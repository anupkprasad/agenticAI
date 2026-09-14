"""Modular PCA/tICA on dihedral or Cartesian features (independent or shared-ref)."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


def _resolve_traj(topology_file: str, trajectory_file: str, sim_directory: Optional[str]):
    from src.analysis.combined_analysis import _find_sim_traj_topology

    top, traj = topology_file, trajectory_file
    if (not top or not Path(top).is_file()) and sim_directory:
        found = _find_sim_traj_topology(str(sim_directory))
        if found[0] and found[1]:
            top, traj = found
    return top, traj


def _load_dihedral_matrix(
    dihedral_dir: Path,
    angles: Sequence[str],
) -> np.ndarray:
    from src.analysis.family_dynamics_core import build_dihedral_feature_matrix

    feat = dihedral_dir / "dihedral_sincos.npy"
    if feat.is_file() and set(a.lower() for a in angles) >= {"phi", "psi", "chi1"}:
        # Full matrix already built with default angles; reload if angles subset needed
        if set(a.lower() for a in angles) == {"phi", "psi", "chi1"}:
            return np.load(feat)
    phi = np.load(dihedral_dir / "phi_deg.npy")
    psi = np.load(dihedral_dir / "psi_deg.npy")
    chi_path = dihedral_dir / "chi1_deg.npy"
    chi = np.load(chi_path) if chi_path.is_file() else None
    has_chi = None
    if chi is not None:
        has_chi = [bool(np.isfinite(chi[:, j]).mean() > 0.1) for j in range(chi.shape[1])]
    return build_dihedral_feature_matrix(
        phi, psi, chi, angles=angles, has_chi1_mask=has_chi
    )


def _load_cartesian_matrix(
    topology_file: str,
    trajectory_file: str,
    alignment_json: str,
    label: str,
    selection: str = "protein and name CA",
) -> np.ndarray:
    """Consensus-mapped Cα coordinates, flattened (n_frames × 3n)."""
    import MDAnalysis as mda
    from MDAnalysis.analysis import align as mda_align

    from src.analysis.family_dynamics_core import (
        load_consensus_alignment,
        mapping_for_label,
    )

    alignment = load_consensus_alignment(alignment_json)
    mapping = mapping_for_label(alignment, label)
    if not mapping:
        raise RuntimeError(f"No mapping for {label}")

    u = mda.Universe(str(Path(topology_file).resolve()), str(Path(trajectory_file).resolve()))
    protein = {int(r.resid): r for r in u.select_atoms("protein").residues}
    resids = []
    for m in mapping:
        if not m or m.get("resid") is None:
            continue
        resid = int(m["resid"])
        if resid in protein:
            resids.append(resid)
    if len(resids) < 5:
        raise RuntimeError(f"Too few mapped Cα residues ({len(resids)})")

    sel = " or ".join(f"resid {r}" for r in resids)
    ag = u.select_atoms(f"({selection}) and ({sel})")
    if ag.n_atoms < 5:
        # fallback: name CA on those residues
        ag = u.select_atoms(f"protein and name CA and ({sel})")
    if ag.n_atoms < 5:
        raise RuntimeError(f"Bad Cα selection n={ag.n_atoms}")

    # Align to frame 0
    ref = u.copy()
    aligner = mda_align.AlignTraj(u, ref, select=f"protein and name CA and ({sel})", in_memory=True)
    aligner.run()

    coords = []
    for _ts in u.trajectory:
        coords.append(ag.positions.copy().reshape(-1))
    return np.asarray(coords, dtype=float)


def _fit_reduce(
    X: np.ndarray,
    *,
    method: str,
    n_components: int,
    lag_frames: int,
    whiten_dim: int,
) -> Dict[str, Any]:
    from src.analysis.family_dynamics_core import fit_pca, fit_pca_whiten, fit_tica

    method = method.lower()
    if method == "pca":
        fit = fit_pca(X, n_components=max(n_components, 2))
        return {
            "method": "pca",
            "mean": fit["mean"],
            "components": fit["components"],
            "projections": fit["projections"],
            "explained_variance_fraction": fit["explained_variance_fraction"],
        }
    if method == "tica":
        Y, mean, Vt, scale = fit_pca_whiten(X, dim=whiten_dim)
        tica = fit_tica(Y, lag=lag_frames, n_tics=max(n_components, 2))
        return {
            "method": "tica",
            "pca_mean": mean,
            "pca_components": Vt,
            "pca_scale": scale,
            "eigenvectors": tica["eigenvectors"],
            "eigenvalues": tica["eigenvalues"],
            "timescales_frames": tica["timescales_frames"],
            "projections": tica["projections"],
            "lag_frames": lag_frames,
        }
    raise ValueError(f"method must be pca or tica, got {method}")


def _project_reduce(X: np.ndarray, model: Dict[str, Any]) -> np.ndarray:
    from src.analysis.family_dynamics_core import project_pca, project_tica

    method = str(model.get("method", "pca")).lower()
    if method == "pca":
        return project_pca(X, model["mean"], model["components"])
    # tica: whiten then project
    Y = (X - model["pca_mean"]) @ model["pca_components"].T
    scale = model["pca_scale"]
    Y = Y / scale
    return project_tica(Y, model["eigenvectors"])


def _write_dynamics_result(
    out_dir: Path,
    proj: np.ndarray,
    *,
    method: str,
    meta_extra: Dict[str, Any],
) -> Dict[str, Any]:
    from src.analysis.family_dynamics_core import fel_descriptors_from_proj2, write_fel_outputs

    if proj.shape[1] < 2:
        raise RuntimeError("Need ≥2 components for FEL")
    desc = fel_descriptors_from_proj2(proj[:, :2])
    paths = write_fel_outputs(
        out_dir, proj=proj[:, :2], desc=desc, method=method, meta_extra=meta_extra
    )
    return {
        "success": True,
        "grid_entropy": desc["grid_entropy"],
        "major_basin_population": desc["major_basin_population"],
        "landscape_entropy": desc["landscape_entropy"],
        "n_basins": desc["n_basins"],
        **paths,
        **meta_extra,
    }


@tool
def run_independent_dynamics_fel(
    space: str = "dihedral",
    method: str = "pca",
    label: str = "",
    topology_file: str = "",
    trajectory_file: str = "",
    alignment_json: str = "",
    dihedral_dir: str = "consensus_dihedrals",
    dihedral_angles: Optional[List[str]] = None,
    selection: str = "protein and name CA",
    lag_frames: int = 10,
    n_components: int = 10,
    whiten_dim: int = 50,
    output_dir: str = "",
    working_dir: Optional[str] = None,
    sim_directory: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Fit PCA or tICA on one simulation and write a 2D FEL + grid entropy.

    **space:** ``dihedral`` (needs prior ``calculate_consensus_torsions``) or
    ``cartesian`` (consensus-mapped Cα; needs ``alignment_json``).

    **method:** ``pca`` or ``tica``.

    Always uses **independent** (per-simulation) projection. For shared-reference
    mode use ``fit_dynamics_model`` then ``project_dynamics_model``.

    Output directory defaults from (space, method): e.g. ``consensus_PCA``,
    ``consensus_TICA``, ``consensus_cart_PCA``, ``consensus_cart_TICA``.
    """
    from src.analysis.family_dynamics_core import dynamics_output_dirname

    original_dir = None
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)

        space_l = space.lower().strip()
        method_l = method.lower().strip()
        out_name = output_dir or dynamics_output_dirname(
            space_l, method_l, "independent"
        )
        out = Path(out_name)
        feat_path = out / "fel_features.json"
        if feat_path.is_file() and not overwrite:
            return {
                "success": True,
                "skipped": True,
                **json.loads(feat_path.read_text(encoding="utf-8")),
                "output_dir": str(out.resolve()),
            }

        angles = list(dihedral_angles or ["phi", "psi", "chi1"])
        if space_l == "dihedral":
            X = _load_dihedral_matrix(Path(dihedral_dir), angles)
        elif space_l == "cartesian":
            if not label or not alignment_json:
                return {
                    "success": False,
                    "error": "cartesian space requires label and alignment_json",
                }
            top, traj = _resolve_traj(topology_file, trajectory_file, sim_directory)
            if not top or not traj:
                return {"success": False, "error": "Missing topology/trajectory"}
            X = _load_cartesian_matrix(top, traj, alignment_json, label, selection)
        else:
            return {"success": False, "error": f"Unknown space={space}"}

        if X.shape[0] < max(lag_frames + 5, 20) or X.shape[1] < 4:
            return {
                "success": False,
                "error": f"Insufficient data shape {X.shape}",
            }

        model = _fit_reduce(
            X,
            method=method_l,
            n_components=n_components,
            lag_frames=lag_frames,
            whiten_dim=whiten_dim,
        )
        proj = model["projections"]
        meta = {
            "label": label,
            "space": space_l,
            "method": method_l,
            "projection_mode": "independent",
            "n_features": int(X.shape[1]),
            "dihedral_angles": angles if space_l == "dihedral" else None,
        }
        result = _write_dynamics_result(out, proj, method=method_l, meta_extra=meta)
        result["output_dir"] = str(out.resolve())
        return result
    except Exception as exc:
        logger.exception("run_independent_dynamics_fel failed")
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)


@tool
def fit_dynamics_model(
    space: str = "dihedral",
    method: str = "pca",
    reference_label: str = "",
    topology_file: str = "",
    trajectory_file: str = "",
    alignment_json: str = "",
    dihedral_dir: str = "",
    dihedral_angles: Optional[List[str]] = None,
    selection: str = "protein and name CA",
    lag_frames: int = 10,
    n_components: int = 10,
    whiten_dim: int = 50,
    model_path: str = "dynamics_model",
    working_dir: Optional[str] = None,
    sim_directory: Optional[str] = None,
    base_directory: str = "",
) -> Dict[str, Any]:
    """
    Fit a shared-reference PCA or tICA model on one reference simulation.

    Use with ``project_dynamics_model`` for family-comparable FELs.
    Saves ``{model_path}.npz`` + ``.json`` under ``working_dir`` (or analysis/).
    """
    from src.analysis.family_dynamics_core import save_model_npz

    if not reference_label:
        return {"success": False, "error": "reference_label is required"}

    original_dir = None
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)

        space_l = space.lower().strip()
        method_l = method.lower().strip()
        angles = list(dihedral_angles or ["phi", "psi", "chi1"])

        # Locate reference sim dihedrals / traj
        ref_sim = None
        if base_directory:
            cand = Path(base_directory) / reference_label
            if cand.is_dir():
                ref_sim = cand
        if sim_directory and Path(sim_directory).is_dir():
            ref_sim = Path(sim_directory)

        if space_l == "dihedral":
            ddir = Path(dihedral_dir) if dihedral_dir else None
            if ddir is None or not ddir.is_dir():
                if ref_sim:
                    ddir = ref_sim / "analysis" / "consensus_dihedrals"
                else:
                    ddir = Path("consensus_dihedrals")
            X = _load_dihedral_matrix(ddir, angles)
        elif space_l == "cartesian":
            if not alignment_json:
                return {"success": False, "error": "alignment_json required for cartesian"}
            top, traj = topology_file, trajectory_file
            if ref_sim:
                top, traj = _resolve_traj(top, traj, str(ref_sim))
            else:
                top, traj = _resolve_traj(top, traj, sim_directory)
            if not top or not traj:
                return {"success": False, "error": "Missing reference trajectory"}
            X = _load_cartesian_matrix(
                top, traj, alignment_json, reference_label, selection
            )
        else:
            return {"success": False, "error": f"Unknown space={space}"}

        model = _fit_reduce(
            X,
            method=method_l,
            n_components=n_components,
            lag_frames=lag_frames,
            whiten_dim=whiten_dim,
        )
        # Drop large projections from saved model (refit not needed for project)
        save_model = {k: v for k, v in model.items() if k != "projections"}
        save_model.update(
            {
                "space": space_l,
                "method": method_l,
                "projection_mode": "shared_reference",
                "reference_label": reference_label,
                "dihedral_angles": angles if space_l == "dihedral" else None,
                "n_features": int(X.shape[1]),
                "selection": selection if space_l == "cartesian" else None,
            }
        )
        out = Path(model_path)
        save_model_npz(out, save_model)
        return {
            "success": True,
            "model_path": str(out.with_suffix(".npz").resolve()),
            "model_meta": str(out.with_suffix(".json").resolve()),
            "space": space_l,
            "method": method_l,
            "reference_label": reference_label,
            "n_features": int(X.shape[1]),
        }
    except Exception as exc:
        logger.exception("fit_dynamics_model failed")
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)


@tool
def project_dynamics_model(
    model_path: str,
    label: str = "",
    topology_file: str = "",
    trajectory_file: str = "",
    alignment_json: str = "",
    dihedral_dir: str = "consensus_dihedrals",
    output_dir: str = "",
    working_dir: Optional[str] = None,
    sim_directory: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Project one simulation onto a fitted shared-reference dynamics model and write FEL.

    ``model_path`` is the stem or ``.npz`` from ``fit_dynamics_model``.
    """
    from src.analysis.family_dynamics_core import (
        dynamics_output_dirname,
        load_model_npz,
    )

    original_dir = None
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)

        model = load_model_npz(Path(model_path))
        space_l = str(model.get("space", "dihedral")).lower()
        method_l = str(model.get("method", "pca")).lower()
        angles = list(model.get("dihedral_angles") or ["phi", "psi", "chi1"])
        out_name = output_dir or dynamics_output_dirname(
            space_l, method_l, "shared_reference"
        )
        out = Path(out_name)
        if (out / "fel_features.json").is_file() and not overwrite:
            return {
                "success": True,
                "skipped": True,
                **json.loads((out / "fel_features.json").read_text(encoding="utf-8")),
                "output_dir": str(out.resolve()),
            }

        if space_l == "dihedral":
            X = _load_dihedral_matrix(Path(dihedral_dir), angles)
        else:
            if not label or not alignment_json:
                return {
                    "success": False,
                    "error": "cartesian projection needs label and alignment_json",
                }
            top, traj = _resolve_traj(topology_file, trajectory_file, sim_directory)
            if not top or not traj:
                return {"success": False, "error": "Missing topology/trajectory"}
            X = _load_cartesian_matrix(
                top,
                traj,
                alignment_json,
                label,
                str(model.get("selection") or "protein and name CA"),
            )

        if X.shape[1] != int(model.get("n_features", X.shape[1])):
            # Allow if close — dihedral χ presence can differ; warn via error if far
            if abs(X.shape[1] - int(model["n_features"])) > 0:
                return {
                    "success": False,
                    "error": (
                        f"Feature dim mismatch: data {X.shape[1]} vs model "
                        f"{model.get('n_features')}. Recompute torsions with same angles/scope."
                    ),
                }

        proj = _project_reduce(X, model)
        meta = {
            "label": label,
            "space": space_l,
            "method": method_l,
            "projection_mode": "shared_reference",
            "reference_label": model.get("reference_label"),
            "model_path": str(Path(model_path).resolve()),
        }
        result = _write_dynamics_result(out, proj, method=method_l, meta_extra=meta)
        result["output_dir"] = str(out.resolve())
        return result
    except Exception as exc:
        logger.exception("project_dynamics_model failed")
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)


@tool
def run_shared_dynamics_fel_batch(
    base_directory: str,
    space: str = "dihedral",
    method: str = "pca",
    reference_label: str = "",
    alignment_json: str = "",
    labels: Optional[List[str]] = None,
    dihedral_angles: Optional[List[str]] = None,
    lag_frames: int = 10,
    n_components: int = 10,
    working_dir: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Fit a shared-reference dynamics model on ``reference_label``, then project all labels.

    Convenience batch for family campaigns. Does not force which features enter
    clustering — only writes FEL artifacts for later collection.
    """
    if not reference_label:
        return {"success": False, "error": "reference_label required"}
    base = Path(base_directory)
    out_root = Path(working_dir) if working_dir else base / "analysis"
    out_root.mkdir(parents=True, exist_ok=True)

    skip = {"analysis", "preprocess", "simsetup", "hpc", "reporter", "programmer"}
    labs = labels or sorted(
        d.name
        for d in base.iterdir()
        if d.is_dir() and d.name.lower() not in skip and not d.name.startswith(".")
    )
    if reference_label not in labs:
        labs = [reference_label] + labs

    model_stem = out_root / f"dynamics_model_{space}_{method}_{reference_label}"
    fit = fit_dynamics_model.invoke(
        {
            "space": space,
            "method": method,
            "reference_label": reference_label,
            "alignment_json": alignment_json,
            "dihedral_angles": dihedral_angles,
            "lag_frames": lag_frames,
            "n_components": n_components,
            "model_path": str(model_stem),
            "working_dir": str(out_root),
            "base_directory": str(base),
            "sim_directory": str(base / reference_label),
        }
    )
    if not fit.get("success"):
        return fit

    results = []
    for lab in labs:
        sim = base / lab
        adir = sim / "analysis"
        adir.mkdir(parents=True, exist_ok=True)
        res = project_dynamics_model.invoke(
            {
                "model_path": fit["model_path"],
                "label": lab,
                "alignment_json": alignment_json,
                "dihedral_dir": "consensus_dihedrals",
                "working_dir": str(adir),
                "sim_directory": str(sim),
                "overwrite": overwrite,
            }
        )
        results.append({"label": lab, **(res if isinstance(res, dict) else {})})

    n_ok = sum(1 for r in results if r.get("success"))
    manifest = {
        "success": n_ok > 0,
        "fit": fit,
        "n_success": n_ok,
        "n_requested": len(labs),
        "results": results,
    }
    (out_root / "shared_dynamics_batch_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8"
    )
    return manifest
