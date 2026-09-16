"""
Reference-projected PCA and shared free-energy landscape clustering.

Workflow (modular tools for agent-driven combined analysis):

  1. ``build_consensus_sequence_alignment`` — MSA + consensus residue map
  2. ``fit_reference_pca_model`` — PCA on reference trajectory consensus Cα
  3. ``project_simulations_reference_pca`` — project all simulations
  4. ``build_shared_reference_fel_landscapes`` — FEL in common PC1/PC2 bins
  5. ``cluster_reference_fel_landscapes`` — cluster + dendrogram + phylo tree
  6. ``run_reference_landscape_pipeline`` — convenience wrapper for steps 2–5
"""
from __future__ import annotations

import csv
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from langchain.tools import tool

from src.analysis.combined_analysis import _find_sim_traj_topology
from src.analysis.pca_analyzer import (
    _KB_KJ_MOL_K,
    _compute_free_energy_grid,
    _fel_surface_levels,
    analyze_fel_landscape_features,
    FEL_BASIN_CMAP,
    FEL_ENERGY_CONTOUR_KJ,
    load_pca_projections,
)

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import align

    HAS_MDA = True
except Exception:  # pragma: no cover
    HAS_MDA = False

try:
    from scipy.cluster import hierarchy
    from scipy.spatial.distance import pdist, squareform

    HAS_SCIPY = True
except Exception:  # pragma: no cover
    HAS_SCIPY = False

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except Exception:  # pragma: no cover
    HAS_MPL = False

DEFAULT_ALIGNMENT_JSON = "reference_msa_alignment.json"
DEFAULT_PCA_MODEL_JSON = "reference_pca_model.json"
# Per-simulation reference-projected outputs live under {working_dir}/reference_fel/{label}/
DEFAULT_REFERENCE_FEL_DIR = "reference_fel"
DEFAULT_PROJECTIONS_DIR = DEFAULT_REFERENCE_FEL_DIR
DEFAULT_FEL_DIR = DEFAULT_REFERENCE_FEL_DIR
DEFAULT_CLUSTER_ASSIGNMENTS = "ref_fel_cluster_assignments.csv"
DEFAULT_CLUSTER_SUMMARY = "ref_fel_clusters.json"
DEFAULT_MIN_COVERAGE = 0.85


def _resolve_display_names(
    labels: Sequence[str],
    *,
    user_goal: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
) -> List[str]:
    from src.analysis.classification_clustering import _apply_display_names

    return _apply_display_names(
        list(labels), user_goal=user_goal, label_name_map=label_name_map
    )


def _mirror_to_sim_analysis(sim_dir: str, src: Path, dest_name: str) -> Optional[str]:
    """Copy an artifact into ``{sim_dir}/analysis/``."""
    if not sim_dir or not src.is_file():
        return None
    dest = Path(sim_dir) / "analysis" / dest_name
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return str(dest)


def _plot_reference_pca_scatter(
    projections: np.ndarray,
    times_ps: np.ndarray,
    output_path: Path,
    *,
    title: str,
    pc_x: int = 1,
    pc_y: int = 2,
) -> None:
    if not HAS_MPL:
        return
    ix, iy = int(pc_x) - 1, int(pc_y) - 1
    if projections.shape[1] <= max(ix, iy):
        return
    x = projections[:, ix]
    y = projections[:, iy]
    t = times_ps[: len(x)] / 1000.0 if len(times_ps) else np.arange(len(x))

    fig, ax = plt.subplots(figsize=(7.5, 6))
    sc = ax.scatter(x, y, c=t, cmap="viridis", s=8, alpha=0.7, edgecolors="none")
    fig.colorbar(sc, ax=ax, label="Time (ns)")
    ax.set_xlabel(f"PC{pc_x} (shared reference)")
    ax.set_ylabel(f"PC{pc_y} (shared reference)")
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _chdir_working(working_dir: Optional[str]) -> Optional[str]:
    if working_dir:
        os.makedirs(working_dir, exist_ok=True)
        original = os.getcwd()
        os.chdir(working_dir)
        return original
    return None


def _restore_cwd(original_dir: Optional[str]) -> None:
    if original_dir:
        os.chdir(original_dir)


def load_consensus_alignment(path: str) -> Dict[str, Any]:
    """Load consensus alignment JSON (legacy or compact v2)."""
    from src.analysis.cross_sim_artifacts import expand_consensus_positions

    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"Consensus alignment JSON not found: {path}"}
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    positions = data.get("consensus_positions") or []
    if not positions:
        positions = expand_consensus_positions(data)
        data = dict(data)
        data["consensus_positions"] = positions
    if len(positions) < 3:
        return {
            "success": False,
            "error": f"Need >=3 consensus positions; found {len(positions)}",
        }
    return {"success": True, "data": data, "consensus_positions": positions}


def _mapping_for_label(
    consensus_positions: Sequence[Dict[str, Any]],
    label: str,
) -> List[Optional[Dict[str, Any]]]:
    """Per-consensus-index mapping dict for ``label`` (None if gap)."""
    out: List[Optional[Dict[str, Any]]] = []
    for pos in consensus_positions:
        mappings = pos.get("mappings") or {}
        out.append(mappings.get(label))
    return out


def _select_ca_by_resids(
    universe: "mda.Universe",
    resids: Sequence[int],
    chain_id: Optional[str] = None,
) -> "mda.AtomGroup":
    """Select Cα atoms in residue order; missing resids are skipped."""
    atoms = []
    for resid in resids:
        sel = f"protein and name CA and resid {int(resid)}"
        if chain_id:
            sel += f" and chainID {chain_id}"
        ag = universe.select_atoms(sel)
        if len(ag) == 1:
            atoms.append(ag[0])
        elif len(ag) > 1:
            atoms.append(ag[0])
    return mda.AtomGroup(atoms, universe)


def _ordered_ca_atoms(
    universe: "mda.Universe",
    chain_id: Optional[str] = None,
) -> List[Any]:
    """Return protein Cα atoms sorted consistently with PDB sequence extraction."""
    sel = "protein and name CA"
    if chain_id:
        sel += f" and chainID {chain_id}"
    atoms = universe.select_atoms(sel)
    if len(atoms) == 0 and chain_id:
        atoms = universe.select_atoms("protein and name CA")
    return sorted(
        atoms,
        key=lambda a: (str(a.chainID), int(a.resid), str(getattr(a, "icode", "") or "")),
    )


def extract_consensus_ca_coords(
    universe: "mda.Universe",
    frame_index: int,
    mapping: Sequence[Optional[Dict[str, Any]]],
    *,
    chain_id: Optional[str] = None,
) -> np.ndarray:
    """Return (n_consensus, 3) Cα coordinates; NaN where residue is unmapped."""
    universe.trajectory[frame_index]
    ca_sorted = _ordered_ca_atoms(universe, chain_id)
    coords = np.full((len(mapping), 3), np.nan, dtype=float)
    for i, m in enumerate(mapping):
        if not m:
            continue
        seq_idx = m.get("seq_index")
        if seq_idx is not None and 0 <= int(seq_idx) < len(ca_sorted):
            coords[i] = ca_sorted[int(seq_idx)].position
            continue
        resid = m.get("resid")
        if resid is None:
            continue
        sel = f"protein and name CA and resid {int(resid)}"
        if chain_id:
            sel += f" and chainID {chain_id}"
        ag = universe.select_atoms(sel)
        if len(ag) >= 1:
            coords[i] = ag[0].position
    return coords


def _kabsch_align_mobile_to_ref(
    mobile: np.ndarray,
    ref: np.ndarray,
) -> np.ndarray:
    """Superpose ``mobile`` (N,3) onto ``ref`` using matched finite rows."""
    mask = np.isfinite(mobile).all(axis=1) & np.isfinite(ref).all(axis=1)
    if mask.sum() < 3:
        return mobile
    m = mobile[mask] - mobile[mask].mean(axis=0)
    r = ref[mask] - ref[mask].mean(axis=0)
    cov = m.T @ r
    v, _s, wt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(wt.T @ v.T))
    dmat = np.diag([1.0, 1.0, d])
    rot = wt.T @ dmat @ v.T
    aligned = mobile.copy()
    centered = mobile[mask] - mobile[mask].mean(axis=0)
    aligned[mask] = centered @ rot + ref[mask].mean(axis=0)
    return aligned


def _trajectory_coord_matrix(
    topology_file: str,
    trajectory_file: str,
    mapping: Sequence[Optional[Dict[str, Any]]],
    *,
    reference_coords: np.ndarray,
    frame_interval: int = 1,
    chain_id: Optional[str] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Return flattened consensus Cα coordinates for each frame (aligned to reference).

    Rows are aligned with Kabsch on finite consensus Cα atoms, then flattened.
    Missing mapped atoms are filled from the reference coordinates after alignment.
    """
    u = mda.Universe(topology_file, trajectory_file)
    rows: List[np.ndarray] = []
    times_ps: List[float] = []
    step = max(1, int(frame_interval))

    for ts in u.trajectory[::step]:
        coords = extract_consensus_ca_coords(u, ts.frame, mapping, chain_id=chain_id)
        aligned = _kabsch_align_mobile_to_ref(coords, reference_coords)
        mask = np.isfinite(aligned).all(axis=1)
        if mask.sum() >= 3:
            rot_center = aligned[mask].mean(axis=0)
            ref_center = reference_coords[mask].mean(axis=0)
            for i in range(aligned.shape[0]):
                if not mask[i]:
                    aligned[i] = reference_coords[i] + (rot_center - ref_center)
        rows.append(aligned.ravel())
        times_ps.append(float(ts.time))

    if not rows:
        return np.zeros((0, 0)), np.asarray(times_ps)
    return np.asarray(rows, dtype=float), np.asarray(times_ps)


def _fit_pca_model(
    X: np.ndarray,
    n_components: int,
) -> Dict[str, Any]:
    """Fit PCA via SVD; return mean, components, variance."""
    if X.shape[0] < 2:
        raise ValueError("Need >=2 frames to fit reference PCA")
    n_components = min(int(n_components), X.shape[0] - 1, X.shape[1])
    mean = X.mean(axis=0)
    Xc = X - mean
    _u, s, vt = np.linalg.svd(Xc, full_matrices=False)
    variance = (s ** 2) / max(X.shape[0] - 1, 1)
    total = variance.sum() or 1.0
    return {
        "mean": mean,
        "components": vt[:n_components],
        "variance": variance[:n_components],
        "cumulative_variance": np.cumsum(variance[:n_components]) / total,
        "n_components": n_components,
    }


def _project_coords(X: np.ndarray, model: Dict[str, Any]) -> np.ndarray:
    Xc = X - model["mean"]
    return Xc @ model["components"].T


def _write_projections_table(
    projections: np.ndarray,
    times_ps: np.ndarray,
    output_path: Path,
) -> None:
    n_pc = projections.shape[1]
    with open(output_path, "w", encoding="utf-8") as fh:
        header = "\t".join(["frame", "time_ns"] + [f"PC{i + 1}" for i in range(n_pc)])
        fh.write(f"# {header}\n")
        for i in range(projections.shape[0]):
            t_ns = times_ps[i] / 1000.0 if i < len(times_ps) else 0.0
            pcs = "\t".join(f"{projections[i, j]:.6f}" for j in range(n_pc))
            fh.write(f"{i}\t{t_ns:.6f}\t{pcs}\n")


def _resolve_chain_id_for_label(
    label: str,
    sim_dir: Optional[str],
    base_dir: str,
    chain_id: Optional[str],
) -> Optional[str]:
    if chain_id:
        return chain_id
    from src.analysis.phylo_tree import resolve_structure_pdb
    from src.preprocess.structure_remodel.sequence_utils import (
        extract_chain_sequences,
        pick_default_chain,
    )

    pdb = resolve_structure_pdb(label, sim_dir, base_dir)
    if not pdb:
        return None
    chains = extract_chain_sequences(pdb)
    return pick_default_chain(chains)


# ── Tools ─────────────────────────────────────────────────────────────────────


@tool
def fit_reference_pca_model(
    reference_label: str,
    working_dir: str,
    consensus_json: str = DEFAULT_ALIGNMENT_JSON,
    sim_dir: str = "",
    topology_file: str = "",
    trajectory_file: str = "",
    base_dir: str = "",
    chain_id: Optional[str] = None,
    n_components: int = 10,
    frame_interval: int = 1,
    reference_frame: int = 0,
    output_model: str = DEFAULT_PCA_MODEL_JSON,
) -> Dict[str, Any]:
    """
    Fit a reference PCA model on consensus Cα coordinates from one trajectory.

    Uses ``consensus_alignment.json`` residue mappings and the reference
    simulation trajectory (or explicit topology/trajectory paths). The model
    is saved for ``project_simulations_reference_pca``.

    Args:
        reference_label: Label of the reference (e.g. ``q8nb16`` for MLKL).
        working_dir: Combined analysis directory with consensus JSON.
        consensus_json: Path to consensus alignment JSON.
        sim_dir: Reference simulation directory (topology/trajectory auto-detected).
        topology_file: Optional explicit topology path.
        trajectory_file: Optional explicit trajectory path.
        base_dir: Base directory for PDB/chain inference.
        chain_id: Optional protein chain ID.
        n_components: Number of principal components to retain.
        frame_interval: Trajectory frame stride.
        reference_frame: Frame index for structural alignment reference.
        output_model: Output JSON model filename.

    Returns:
        Dict with ``success``, ``model_file``, variance explained, ``n_consensus_atoms``.
    """
    if not HAS_MDA:
        return {"success": False, "error": "MDAnalysis is required for reference PCA"}

    out_dir = Path(working_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cpath = Path(consensus_json)
    if not cpath.is_absolute():
        cpath = out_dir / consensus_json

    loaded = load_consensus_alignment(str(cpath))
    if not loaded.get("success"):
        return loaded

    consensus = loaded["consensus_positions"]
    mapping = _mapping_for_label(consensus, reference_label)
    if sum(1 for m in mapping if m) < 3:
        return {
            "success": False,
            "error": f"Reference {reference_label} has <3 mapped consensus residues",
        }

    topo = trajectory = None
    if topology_file and trajectory_file:
        topo, trajectory = topology_file, trajectory_file
    elif sim_dir:
        topo, trajectory = _find_sim_traj_topology(sim_dir)
    if not topo or not trajectory:
        return {
            "success": False,
            "error": "Provide sim_dir or topology_file+trajectory_file for reference",
        }

    cid = _resolve_chain_id_for_label(
        reference_label, sim_dir or None, base_dir or str(out_dir.parent), chain_id
    )

    try:
        u = mda.Universe(topo, trajectory)
        ref_idx = max(0, min(int(reference_frame), len(u.trajectory) - 1))
        ref_coords = extract_consensus_ca_coords(
            u, ref_idx, mapping, chain_id=cid
        )
        n_finite_atoms = int(np.isfinite(ref_coords).all(axis=1).sum())
        if n_finite_atoms < 3:
            return {
                "success": False,
                "error": (
                    f"Too few finite consensus Cα atoms on reference frame "
                    f"({n_finite_atoms} mapped; need >=3)"
                ),
            }

        X, times_ps = _trajectory_coord_matrix(
            topo,
            trajectory,
            mapping,
            reference_coords=ref_coords,
            frame_interval=frame_interval,
            chain_id=cid,
        )
        if X.shape[0] < 2:
            return {"success": False, "error": "Reference trajectory has <2 usable frames"}

        model = _fit_pca_model(X, n_components)
        model_path = out_dir / output_model
        payload = {
            "reference_label": reference_label,
            "consensus_json": str(cpath.name),
            "n_consensus_positions": len(consensus),
            "n_consensus_atoms": int(np.isfinite(ref_coords).all(axis=1).sum()),
            "chain_id": cid,
            "topology_file": topo,
            "trajectory_file": trajectory,
            "n_components": model["n_components"],
            "variance": model["variance"].tolist(),
            "cumulative_variance": model["cumulative_variance"].tolist(),
            "mean": model["mean"].tolist(),
            "components": model["components"].tolist(),
            "reference_resids": [
                (m or {}).get("resid") for m in mapping
            ],
        }
        with open(model_path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        return {
            "success": True,
            "message": (
                f"Reference PCA model fitted on {reference_label} "
                f"({model['n_components']} PCs, "
                f"{payload['n_consensus_atoms']} consensus Cα atoms)"
            ),
            "model_file": str(model_path),
            "reference_label": reference_label,
            "n_components": model["n_components"],
            "pc1_variance_fraction": float(model["cumulative_variance"][0])
            if len(model["cumulative_variance"])
            else 0.0,
            "n_consensus_atoms": payload["n_consensus_atoms"],
            "n_frames": int(X.shape[0]),
        }
    except Exception as exc:
        logger.exception("fit_reference_pca_model failed")
        return {"success": False, "error": str(exc)}


@tool
def project_simulations_reference_pca(
    sim_dirs: List[str],
    labels: List[str],
    working_dir: str,
    model_file: str = DEFAULT_PCA_MODEL_JSON,
    consensus_json: str = DEFAULT_ALIGNMENT_JSON,
    base_dir: str = "",
    chain_id: Optional[str] = None,
    frame_interval: int = 1,
    output_subdir: str = DEFAULT_PROJECTIONS_DIR,
    user_goal: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
    pc_x: int = 1,
    pc_y: int = 2,
    mirror_per_sim: bool = False,
) -> Dict[str, Any]:
    """
    Project trajectories onto a saved reference PCA model (consensus Cα).

    Writes per-simulation ``reference_pca_projections.dat`` under
    ``{working_dir}/reference_fel/{label}/`` (combined analysis only; not mirrored
    into per-simulation ``analysis/`` unless ``mirror_per_sim=True``).

    Args:
        sim_dirs: Per-simulation directories (parallel to ``labels``).
        labels: Simulation labels.
        working_dir: Combined analysis directory.
        model_file: JSON model from ``fit_reference_pca_model``.
        consensus_json: Consensus alignment JSON.
        base_dir: Base directory for chain ID inference.
        chain_id: Optional chain ID override for all simulations.
        frame_interval: Frame stride when reading trajectories.
        output_subdir: Subdirectory for per-label projection files.
        user_goal: Optional goal text to parse ``id:name`` display labels.
        label_name_map: Optional explicit label → protein name map.
        pc_x: PC for scatter horizontal axis (1-based).
        pc_y: PC for scatter vertical axis (1-based).

    Returns:
        Dict with ``success``, ``projections`` map label → file path, ``missing``.
    """
    if not HAS_MDA:
        return {"success": False, "error": "MDAnalysis is required for projection"}

    out_dir = Path(working_dir)
    model_path = Path(model_file)
    if not model_path.is_absolute():
        model_path = out_dir / model_file
    if not model_path.is_file():
        return {"success": False, "error": f"PCA model not found: {model_path}"}

    cpath = Path(consensus_json)
    if not cpath.is_absolute():
        cpath = out_dir / consensus_json
    loaded = load_consensus_alignment(str(cpath))
    if not loaded.get("success"):
        return loaded

    with open(model_path, encoding="utf-8") as fh:
        model_data = json.load(fh)

    model = {
        "mean": np.asarray(model_data["mean"], dtype=float),
        "components": np.asarray(model_data["components"], dtype=float),
    }
    ref_label = model_data.get("reference_label", "")
    consensus = loaded["consensus_positions"]

    proj_root = out_dir / output_subdir
    proj_root.mkdir(parents=True, exist_ok=True)

    display_names = _resolve_display_names(
        labels, user_goal=user_goal, label_name_map=label_name_map
    )
    display_by_label = {str(l): d for l, d in zip(labels, display_names)}

    projections_out: Dict[str, str] = {}
    per_sim_outputs: Dict[str, Dict[str, str]] = {}
    missing: List[str] = []
    errors: Dict[str, str] = {}

    # Reference coords from model topology at frame 0
    ref_topo = model_data.get("topology_file")
    ref_traj = model_data.get("trajectory_file")
    ref_mapping = _mapping_for_label(consensus, ref_label)
    ref_cid = model_data.get("chain_id")
    ref_coords = None
    if ref_topo and ref_traj:
        u_ref = mda.Universe(ref_topo, ref_traj)
        ref_coords = extract_consensus_ca_coords(u_ref, 0, ref_mapping, chain_id=ref_cid)

    for sim_dir, label in zip(sim_dirs, labels):
        mapping = _mapping_for_label(consensus, label)
        if sum(1 for m in mapping if m) < 3:
            missing.append(label)
            continue
        topo, traj = _find_sim_traj_topology(sim_dir)
        if not topo or not traj:
            missing.append(label)
            errors[label] = "topology/trajectory not found"
            continue
        cid = chain_id or _resolve_chain_id_for_label(
            label, sim_dir, base_dir or str(out_dir.parent), None
        )
        try:
            if ref_coords is None:
                u0 = mda.Universe(topo, traj)
                ref_coords = extract_consensus_ca_coords(u0, 0, mapping, chain_id=cid)
            X, times_ps = _trajectory_coord_matrix(
                topo,
                traj,
                mapping,
                reference_coords=ref_coords,
                frame_interval=frame_interval,
                chain_id=cid,
            )
            if X.shape[0] < 1:
                missing.append(label)
                errors[label] = "no frames"
                continue
            proj = _project_coords(X, model)
            label_dir = proj_root / label
            label_dir.mkdir(parents=True, exist_ok=True)
            out_file = label_dir / "reference_pca_projections.dat"
            _write_projections_table(proj, times_ps, out_file)
            projections_out[label] = str(out_file)

            disp = display_by_label.get(str(label), str(label))
            scatter_path = label_dir / "reference_pca_pc1_pc2.png"
            _plot_reference_pca_scatter(
                proj,
                times_ps,
                scatter_path,
                title=f"{disp} — reference-projected PCA",
                pc_x=pc_x,
                pc_y=pc_y,
            )

            sim_paths: Dict[str, str] = {}
            mirrored_proj = (
                _mirror_to_sim_analysis(sim_dir, out_file, "reference_pca_projections.dat")
                if mirror_per_sim
                else None
            )
            if mirrored_proj:
                sim_paths["projections"] = mirrored_proj
            if scatter_path.is_file():
                mirrored_plot = (
                    _mirror_to_sim_analysis(sim_dir, scatter_path, "reference_pca_pc1_pc2.png")
                    if mirror_per_sim
                    else None
                )
                if mirrored_plot:
                    sim_paths["pca_plot"] = mirrored_plot
            if sim_paths:
                per_sim_outputs[str(label)] = sim_paths
        except Exception as exc:
            logger.warning("Projection failed for %s: %s", label, exc)
            missing.append(label)
            errors[label] = str(exc)

    if len(projections_out) < 2:
        return {
            "success": False,
            "error": f"Projected <2 simulations; missing={missing}",
            "missing": missing,
            "errors": errors,
        }

    manifest = {
        "model_file": str(model_path),
        "reference_label": ref_label,
        "projections": projections_out,
        "sim_directories": {str(l): str(d) for l, d in zip(labels, sim_dirs)},
        "display_names": display_by_label,
        "per_sim_outputs": per_sim_outputs,
        "missing": missing,
    }
    manifest_path = proj_root / "reference_pca_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)

    return {
        "success": True,
        "message": f"Projected {len(projections_out)} simulations onto reference PCA",
        "manifest_file": str(manifest_path),
        "projections": projections_out,
        "per_sim_outputs": per_sim_outputs,
        "n_projected": len(projections_out),
        "missing": missing,
    }


@tool
def build_shared_reference_fel_landscapes(
    working_dir: str,
    labels: Optional[List[str]] = None,
    projections_subdir: str = DEFAULT_PROJECTIONS_DIR,
    pc_x: int = 1,
    pc_y: int = 2,
    bins: int = 50,
    temperature_k: float = 310.0,
    output_subdir: str = DEFAULT_FEL_DIR,
    features_subdir: str = DEFAULT_REFERENCE_FEL_DIR,
    user_goal: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
    mirror_per_sim: bool = False,
    min_basin_population: float = 0.05,
) -> Dict[str, Any]:
    """
    Build free-energy landscapes in a **shared** PC1/PC2 grid for all projections.

    Reads ``reference_pca_projections.dat`` per label, defines global bin edges
    from pooled PC ranges, and writes per-simulation FEL PNG/CSV plus
    ``analyze_fel_landscape_features`` JSON summaries.

    Args:
        working_dir: Combined analysis directory.
        labels: Optional subset of labels (default: all in manifest).
        projections_subdir: Directory with projected PCA files.
        pc_x: Horizontal PC (1-based).
        pc_y: Vertical PC (1-based).
        bins: Histogram bins per axis.
        temperature_k: Temperature for kT in kJ/mol.
        output_subdir: Output directory for shared FEL grids/plots.
        features_subdir: Subdirectory for per-sim FEL feature JSON (default: reference_fel).
        user_goal: Optional goal text to parse ``id:name`` display labels.
        label_name_map: Optional explicit label → protein name map.
        mirror_per_sim: When True, copy artifacts into ``{sim_dir}/analysis/`` (default False).
        min_basin_population: Minimum basin occupancy fraction (default 5%).

    Returns:
        Dict with ``success``, per-label FEL paths, global bin ranges.
    """
    if not HAS_MPL:
        return {"success": False, "error": "matplotlib is required for FEL plots"}

    out_dir = Path(working_dir)
    proj_root = out_dir / projections_subdir
    manifest_path = proj_root / "reference_pca_manifest.json"
    manifest: Dict[str, Any] = {}
    if manifest_path.is_file():
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        proj_map = manifest.get("projections") or {}
    else:
        proj_map = {}
        if proj_root.is_dir():
            for d in sorted(proj_root.iterdir()):
                p = d / "reference_pca_projections.dat"
                if p.is_file():
                    proj_map[d.name] = str(p)

    sim_dirs_map: Dict[str, str] = manifest.get("sim_directories") or {}
    display_by_label: Dict[str, str] = dict(manifest.get("display_names") or {})
    if not display_by_label and proj_map:
        resolved = _resolve_display_names(
            list(proj_map.keys()), user_goal=user_goal, label_name_map=label_name_map
        )
        display_by_label = {str(l): d for l, d in zip(proj_map.keys(), resolved)}

    if labels:
        proj_map = {k: v for k, v in proj_map.items() if k in labels}

    if len(proj_map) < 2:
        return {"success": False, "error": "Need >=2 projection files for shared FEL"}

    ix, iy = int(pc_x) - 1, int(pc_y) - 1
    pc_data: Dict[str, np.ndarray] = {}
    for label, path in proj_map.items():
        loaded = load_pca_projections(path)
        if not loaded.get("success"):
            continue
        proj = loaded["projections"]
        if ix >= proj.shape[1] or iy >= proj.shape[1]:
            continue
        pc_data[label] = proj[:, [ix, iy]]

    if len(pc_data) < 2:
        return {"success": False, "error": "Insufficient valid PC projections"}

    all_x = np.concatenate([v[:, 0] for v in pc_data.values()])
    all_y = np.concatenate([v[:, 1] for v in pc_data.values()])
    xedges = np.linspace(float(all_x.min()), float(all_x.max()), int(bins) + 1)
    yedges = np.linspace(float(all_y.min()), float(all_y.max()), int(bins) + 1)

    fel_root = out_dir / output_subdir
    feat_root = out_dir / features_subdir
    fel_root.mkdir(parents=True, exist_ok=True)

    fel_outputs: Dict[str, Dict[str, str]] = {}
    per_sim_fel_outputs: Dict[str, Dict[str, str]] = {}
    feature_rows: List[Dict[str, Any]] = []

    for label, pcs in pc_data.items():
        disp = display_by_label.get(str(label), str(label))
        H, _, _ = np.histogram2d(pcs[:, 0], pcs[:, 1], bins=[xedges, yedges])
        total = H.sum()
        if total <= 0:
            continue
        P = H / total
        kT = _KB_KJ_MOL_K * float(temperature_k)
        F = -kT * np.log(P + 1e-12)
        F = F - np.nanmin(F)

        label_dir = fel_root / label
        label_dir.mkdir(parents=True, exist_ok=True)
        grid_csv = label_dir / f"reference_fel_pc{pc_x}_pc{pc_y}_grid.csv"
        plot_png = label_dir / f"reference_fel_pc{pc_x}_pc{pc_y}.png"

        xc = 0.5 * (xedges[:-1] + xedges[1:])
        yc = 0.5 * (yedges[:-1] + yedges[1:])
        with open(grid_csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(
                [f"PC{pc_x}", f"PC{pc_y}", "free_energy_kJ_mol", "probability"]
            )
            for j in range(F.shape[0]):
                for i in range(F.shape[1]):
                    writer.writerow([
                        f"{xc[i]:.6f}",
                        f"{yc[j]:.6f}",
                        f"{F[j, i]:.6f}",
                        f"{P[j, i]:.6e}",
                    ])

        X, Y = np.meshgrid(xc, yc)
        fig, ax = plt.subplots(figsize=(7.5, 6))
        F_plot = F.astype(float).copy()
        F_plot[P <= 0] = np.nan
        finite = F_plot[np.isfinite(F_plot)]
        if finite.size:
            F_plot = F_plot - float(np.nanmin(finite))
        levels, vmin, vmax = _fel_surface_levels(F_plot, P)
        cf = ax.contourf(
            X, Y, F_plot, levels=levels, cmap=FEL_BASIN_CMAP,
            vmin=vmin, vmax=vmax, extend="max",
        )
        iso = [lv for lv in FEL_ENERGY_CONTOUR_KJ if vmin < lv < vmax]
        if iso:
            ax.contour(X, Y, F_plot, levels=iso, colors="0.15", linewidths=0.45, alpha=0.55)
        ax.set_facecolor("0.97")
        fig.colorbar(cf, ax=ax, label="Relative free energy (kJ/mol)")
        ax.set_xlabel(f"PC{pc_x} (shared ref)")
        ax.set_ylabel(f"PC{pc_y} (shared ref)")
        ax.set_title(f"{disp} — shared reference FEL")
        fig.tight_layout()
        fig.savefig(plot_png, dpi=150, bbox_inches="tight")
        plt.close(fig)

        feat_dir = label_dir
        feat_res = analyze_fel_landscape_features.func(
            working_dir=str(feat_dir),
            fel_grid_file=str(grid_csv.resolve()),
            pc_x=pc_x,
            pc_y=pc_y,
            bins=bins,
            temperature_k=temperature_k,
            min_basin_population=min_basin_population,
        )
        basin_plot = feat_dir / "fel_basins.png"
        reference_basin_plot = feat_dir / "reference_fel_basins.png"
        if basin_plot.is_file():
            basin_plot.replace(reference_basin_plot)
        fel_outputs[label] = {
            "grid_csv": str(grid_csv),
            "plot_png": str(plot_png),
            "features_json": str(feat_dir / "fel_features.json"),
            "basins_plot": (
                str(reference_basin_plot) if reference_basin_plot.is_file() else ""
            ),
        }
        if feat_res.get("success"):
            feature_rows.append({
                "label": label,
                "display_name": disp,
                "n_basins": feat_res.get("n_minima"),
                "n_minima_detected": feat_res.get("n_minima_detected"),
                "landscape_entropy": feat_res.get("landscape_entropy"),
                "major_basin_population": feat_res.get("major_basin_population"),
                "max_barrier_height_kJ_mol": feat_res.get("max_barrier_height_kJ_mol"),
                "mean_basin_depth_kJ_mol": feat_res.get("mean_basin_depth_kJ_mol"),
                "grid_entropy": feat_res.get("grid_entropy"),
            })

        if mirror_per_sim:
            sim_dir = sim_dirs_map.get(str(label)) or sim_dirs_map.get(label, "")
            sim_paths: Dict[str, str] = {}
            for src, dest in (
                (plot_png, f"reference_fel_pc{pc_x}_pc{pc_y}.png"),
                (grid_csv, f"reference_fel_pc{pc_x}_pc{pc_y}_grid.csv"),
            ):
                mirrored = _mirror_to_sim_analysis(sim_dir, src, dest)
                if mirrored:
                    sim_paths[dest] = mirrored
            for src_name, dest_name in (
                ("fel_features.json", "reference_fel_features.json"),
                ("reference_fel_basins.png", "reference_fel_basins.png"),
            ):
                src = feat_dir / src_name
                mirrored = _mirror_to_sim_analysis(sim_dir, src, dest_name)
                if mirrored:
                    sim_paths[dest_name] = mirrored
            if sim_paths:
                per_sim_fel_outputs[str(label)] = sim_paths
                fel_outputs[label]["per_sim"] = sim_paths

    summary_path = out_dir / "ref_fel_features_table.json"
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(feature_rows, fh, indent=2)

    return {
        "success": True,
        "message": f"Built shared FEL for {len(fel_outputs)} simulations",
        "n_fel": len(fel_outputs),
        "fel_outputs": fel_outputs,
        "per_sim_fel_outputs": per_sim_fel_outputs,
        "features_table": str(summary_path),
        "shared_bin_ranges": {
            f"PC{pc_x}": [float(xedges[0]), float(xedges[-1])],
            f"PC{pc_y}": [float(yedges[0]), float(yedges[-1])],
        },
    }


@tool
def cluster_reference_fel_landscapes(
    working_dir: str,
    features_table: str = "ref_fel_features_table.json",
    method: str = "hierarchical",
    n_clusters: Optional[int] = None,
    linkage_method: str = "ward",
    assignments_file: str = DEFAULT_CLUSTER_ASSIGNMENTS,
    dendrogram_file: str = "ref_fel_dendrogram.png",
    phylo_tree_file: str = "ref_fel_phylo_tree.png",
    summary_file: str = DEFAULT_CLUSTER_SUMMARY,
    user_goal: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Cluster simulations from shared-reference FEL feature summaries.

    Uses landscape entropy, basin count, major basin population, barriers,
    and mean basin depth from ``reference_fel_features_table.json``.

    Args:
        working_dir: Combined analysis directory.
        features_table: JSON feature table from ``build_shared_reference_fel_landscapes``.
        method: ``hierarchical`` (default) or ``kmeans``.
        n_clusters: Number of clusters (auto if omitted).
        linkage_method: scipy linkage method for hierarchical clustering.
        assignments_file: Output CSV with cluster assignments.
        dendrogram_file: Dendrogram PNG (hierarchical only).
        phylo_tree_file: Circular phylogram PNG (hierarchical only).
        summary_file: JSON summary.
        user_goal: Optional goal text for display-name parsing.
        label_name_map: Optional label → protein name map.

    Returns:
        Dict with ``success``, cluster assignments path, plot paths.
    """
    if not HAS_SCIPY:
        return {"success": False, "error": "scipy is required for clustering"}

    from src.analysis.classification_clustering import (
        _apply_display_names,
        _cluster_hierarchical,
        _cluster_kmeans,
        _default_n_clusters,
        _parse_n_clusters_from_text,
        _plot_dendrogram,
        _plot_unrooted_phylo_tree,
    )

    out_dir = Path(working_dir)
    feat_path = Path(features_table)
    if not feat_path.is_absolute():
        feat_path = out_dir / features_table
    if not feat_path.is_file():
        return {"success": False, "error": f"Features table not found: {feat_path}"}

    with open(feat_path, encoding="utf-8") as fh:
        rows = json.load(fh)
    if len(rows) < 2:
        return {"success": False, "error": "Need >=2 simulations in features table"}

    feature_keys = [
        "n_basins",
        "landscape_entropy",
        "major_basin_population",
        "max_barrier_height_kJ_mol",
        "mean_basin_depth_kJ_mol",
        "grid_entropy",
    ]
    labels = [str(r.get("label", f"sim{i}")) for i, r in enumerate(rows)]
    display_names = [
        str(r.get("display_name"))
        if r.get("display_name")
        else None
        for r in rows
    ]
    if not any(display_names):
        display_names = _apply_display_names(
            labels, user_goal=user_goal, label_name_map=label_name_map
        )
    else:
        fallback = _apply_display_names(
            labels, user_goal=user_goal, label_name_map=label_name_map
        )
        display_names = [
            d or fb for d, fb in zip(display_names, fallback)
        ]

    X_list: List[List[float]] = []
    kept_labels: List[str] = []
    kept_display: List[str] = []
    for row, lab, disp in zip(rows, labels, display_names):
        vec = []
        ok = True
        for key in feature_keys:
            val = row.get(key)
            if val is None:
                ok = False
                break
            vec.append(float(val))
        if ok:
            X_list.append(vec)
            kept_labels.append(lab)
            kept_display.append(disp)

    if len(X_list) < 2:
        return {"success": False, "error": "Insufficient complete FEL feature rows"}

    X = np.asarray(X_list, dtype=float)
    col_mean = np.nanmean(X, axis=0)
    col_std = np.nanstd(X, axis=0)
    col_std[col_std < 1e-12] = 1.0
    Xz = (X - col_mean) / col_std

    n_samples = Xz.shape[0]
    k = n_clusters or _parse_n_clusters_from_text(user_goal) or _default_n_clusters(n_samples)
    k = max(1, min(k, n_samples))

    method_key = "kmeans" if (method or "").lower().replace("-", "") in ("kmeans", "kmean") else "hierarchical"
    linkage_matrix = None
    if method_key == "hierarchical":
        cluster_ids, linkage_matrix = _cluster_hierarchical(Xz, k, linkage_method=linkage_method)
    else:
        cluster_ids = _cluster_kmeans(Xz, k)

    assign_path = out_dir / assignments_file
    with open(assign_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["label", "display_name", "cluster_id", "method"])
        for lab, disp, cid in zip(kept_labels, kept_display, cluster_ids):
            writer.writerow([lab, disp, int(cid), method_key])

    dendro_path = phylo_path = None
    if method_key == "hierarchical" and linkage_matrix is not None and HAS_MPL:
        dendro_path = out_dir / dendrogram_file
        _plot_dendrogram(
            linkage_matrix,
            kept_display,
            dendro_path,
            title=f"Reference FEL clustering dendrogram (k={k})",
            cluster_ids=cluster_ids,
            n_clusters=k,
        )
        phylo_path = out_dir / phylo_tree_file
        _plot_unrooted_phylo_tree(
            linkage_matrix,
            kept_display,
            cluster_ids,
            phylo_path,
            title=f"Reference FEL phylogenetic tree (k={k})",
        )

    summary = {
        "method": method_key,
        "n_clusters": k,
        "linkage_method": linkage_method if method_key == "hierarchical" else None,
        "feature_keys": feature_keys,
        "labels": kept_labels,
        "cluster_ids": cluster_ids.tolist(),
    }
    summary_path = out_dir / summary_file
    with open(summary_path, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    return {
        "success": True,
        "message": f"Clustered {len(kept_labels)} simulations into k={k}",
        "assignments_file": str(assign_path),
        "dendrogram_plot": str(dendro_path) if dendro_path else None,
        "phylo_tree_plot": str(phylo_path) if phylo_path else None,
        "summary_file": str(summary_path),
        "n_clusters": k,
        "n_samples": len(kept_labels),
    }


@tool
def run_reference_landscape_pipeline(
    sim_dirs: List[str],
    labels: List[str],
    working_dir: str,
    reference_label: str,
    base_dir: str = "",
    min_coverage: float = DEFAULT_MIN_COVERAGE,
    n_clusters: Optional[int] = None,
    user_goal: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
    chain_id: Optional[str] = None,
    frame_interval: int = 1,
    n_components: int = 10,
    bins: int = 50,
    temperature_k: float = 310.0,
    min_basin_population: float = 0.05,
) -> Dict[str, Any]:
    """
    Convenience wrapper: consensus alignment → reference PCA → shared FEL → clustering.

    Runs ``build_consensus_sequence_alignment``, ``fit_reference_pca_model``,
    ``project_simulations_reference_pca``, ``build_shared_reference_fel_landscapes``,
    and ``cluster_reference_fel_landscapes`` in sequence.

    Args:
        sim_dirs: Per-simulation directories.
        labels: Simulation labels (``reference_label`` must be included).
        working_dir: Combined analysis output directory.
        reference_label: Reference sequence/trajectory label (e.g. ``q8nb16`` MLKL).
        base_dir: Base multi-simulation directory.
        min_coverage: Consensus alignment coverage threshold.
        n_clusters: Optional cluster count for FEL clustering.
        user_goal: Optional goal text for labels and cluster count parsing.
        label_name_map: Optional display name map.
        chain_id: Optional protein chain ID for PDBs.
        frame_interval: Trajectory frame stride.
        n_components: PCs in reference model.
        bins: FEL histogram bins.
        temperature_k: FEL temperature (K).
        min_basin_population: Minimum basin occupancy fraction for FEL features (default 5%).

    Returns:
        Dict with ``success`` and paths from each pipeline stage.
    """
    from src.analysis.consensus_alignment import build_consensus_sequence_alignment

    ref_sim = None
    for sd, lab in zip(sim_dirs, labels):
        if str(lab) == str(reference_label):
            ref_sim = sd
            break
    if not ref_sim:
        return {
            "success": False,
            "error": f"reference_label {reference_label!r} not in labels/sim_dirs",
        }

    align_res = build_consensus_sequence_alignment.func(
        working_dir=working_dir,
        reference_label=reference_label,
        labels=labels,
        sim_dirs=sim_dirs,
        base_dir=base_dir,
        min_coverage=min_coverage,
        chain_id=chain_id,
    )
    if not align_res.get("success"):
        return {"success": False, "stage": "alignment", **align_res}

    fit_res = fit_reference_pca_model.func(
        reference_label=reference_label,
        working_dir=working_dir,
        sim_dir=ref_sim,
        base_dir=base_dir,
        chain_id=chain_id,
        n_components=n_components,
        frame_interval=frame_interval,
    )
    if not fit_res.get("success"):
        return {"success": False, "stage": "fit_pca", **fit_res}

    proj_res = project_simulations_reference_pca.func(
        sim_dirs=sim_dirs,
        labels=labels,
        working_dir=working_dir,
        base_dir=base_dir,
        chain_id=chain_id,
        frame_interval=frame_interval,
        user_goal=user_goal,
        label_name_map=label_name_map,
    )
    if not proj_res.get("success"):
        return {"success": False, "stage": "project_pca", **proj_res}

    fel_res = build_shared_reference_fel_landscapes.func(
        working_dir=working_dir,
        bins=bins,
        temperature_k=temperature_k,
        user_goal=user_goal,
        label_name_map=label_name_map,
        min_basin_population=min_basin_population,
    )
    if not fel_res.get("success"):
        return {"success": False, "stage": "shared_fel", **fel_res}

    clust_res = cluster_reference_fel_landscapes.func(
        working_dir=working_dir,
        n_clusters=n_clusters,
        user_goal=user_goal,
        label_name_map=label_name_map,
    )
    if not clust_res.get("success"):
        return {"success": False, "stage": "cluster", **clust_res}

    return {
        "success": True,
        "message": (
            f"Reference landscape pipeline complete for {len(labels)} simulations "
            f"(reference={reference_label})"
        ),
        "alignment": align_res,
        "pca_model": fit_res,
        "projections": proj_res,
        "fel": fel_res,
        "clustering": clust_res,
    }
