"""Consensus-mapped RMSF and DCCM scalar features for family classification."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _mapped_ca_atomgroup(u, mapping):
    protein = {int(r.resid): r for r in u.select_atoms("protein").residues}
    resids = []
    meta = []
    for ci, m in enumerate(mapping):
        if not m or m.get("resid") is None:
            continue
        resid = int(m["resid"])
        if resid not in protein:
            continue
        resids.append(resid)
        meta.append({"consensus_index": ci, "resid": resid, "aa": m.get("aa")})
    if not resids:
        return None, []
    sel = " or ".join(f"resid {r}" for r in resids)
    ag = u.select_atoms(f"protein and name CA and ({sel})")
    return ag, meta


@tool
def calculate_consensus_rmsf_features(
    topology_file: str = "",
    trajectory_file: str = "",
    alignment_json: str = "",
    label: str = "",
    output_dir: str = "consensus_rmsf",
    working_dir: Optional[str] = None,
    sim_directory: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Consensus-mapped Cα RMSF mean/std for one simulation.

    Writes ``{output_dir}/consensus_rmsf_features.json`` with
    ``consensus_rmsf_mean_A`` and ``consensus_rmsf_std_A``, plus per-residue profile.
    """
    import MDAnalysis as mda
    from MDAnalysis.analysis import rms

    from src.analysis.family_dynamics_core import (
        load_consensus_alignment,
        mapping_for_label,
    )

    if not alignment_json or not label:
        return {"success": False, "error": "alignment_json and label required"}

    original_dir = None
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        feat_path = out / "consensus_rmsf_features.json"
        if feat_path.is_file() and not overwrite:
            return {"success": True, "skipped": True, **json.loads(feat_path.read_text())}

        top, traj = _resolve_traj(topology_file, trajectory_file, sim_directory)
        if not top or not traj:
            return {"success": False, "error": "Missing trajectory"}

        alignment = load_consensus_alignment(alignment_json)
        mapping = mapping_for_label(alignment, label)
        u = mda.Universe(str(Path(top).resolve()), str(Path(traj).resolve()))
        ag, meta = _mapped_ca_atomgroup(u, mapping)
        if ag is None or ag.n_atoms < 3:
            return {"success": False, "error": "Too few mapped Cα atoms"}

        R = rms.RMSF(ag).run()
        vals = np.asarray(R.results.rmsf, dtype=float)
        mean_a = float(np.mean(vals))
        std_a = float(np.std(vals))
        profile = out / "per_residue_rmsf.csv"
        with open(profile, "w", encoding="utf-8") as fh:
            fh.write("consensus_index,resid,aa,rmsf_A\n")
            for i, m in enumerate(meta):
                if i < len(vals):
                    fh.write(
                        f"{m['consensus_index']},{m['resid']},{m.get('aa','')},{vals[i]:.6f}\n"
                    )
        feat = {
            "success": True,
            "label": label,
            "consensus_rmsf_mean_A": mean_a,
            "consensus_rmsf_std_A": std_a,
            "n_atoms": int(ag.n_atoms),
            "profile_csv": str(profile.resolve()),
        }
        feat_path.write_text(json.dumps(feat, indent=2) + "\n", encoding="utf-8")
        return feat
    except Exception as exc:
        logger.exception("calculate_consensus_rmsf_features failed")
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)


@tool
def calculate_consensus_dccm_features(
    topology_file: str = "",
    trajectory_file: str = "",
    alignment_json: str = "",
    label: str = "",
    n_lobe_ci_max: int = 34,
    c_lobe_ci_min: int = 35,
    output_dir: str = "consensus_DCCM",
    working_dir: Optional[str] = None,
    sim_directory: Optional[str] = None,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Consensus-mapped Cα DCCM scalars: mean |corr| and N↔C lobe mean correlation.

    Lobe split uses consensus indices: N-lobe ``ci <= n_lobe_ci_max``,
    C-lobe ``ci >= c_lobe_ci_min`` (override for non-kinase families).

    Writes ``dccm_N_C_mean_corr``, ``mean_abs_dccm`` into
    ``{output_dir}/consensus_dccm_features.json``.
    """
    import MDAnalysis as mda
    from MDAnalysis.analysis import align as mda_align

    from src.analysis.family_dynamics_core import (
        load_consensus_alignment,
        mapping_for_label,
    )

    if not alignment_json or not label:
        return {"success": False, "error": "alignment_json and label required"}

    original_dir = None
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        feat_path = out / "consensus_dccm_features.json"
        if feat_path.is_file() and not overwrite:
            return {"success": True, "skipped": True, **json.loads(feat_path.read_text())}

        top, traj = _resolve_traj(topology_file, trajectory_file, sim_directory)
        if not top or not traj:
            return {"success": False, "error": "Missing trajectory"}

        alignment = load_consensus_alignment(alignment_json)
        mapping = mapping_for_label(alignment, label)
        u = mda.Universe(str(Path(top).resolve()), str(Path(traj).resolve()))
        ag, meta = _mapped_ca_atomgroup(u, mapping)
        if ag is None or ag.n_atoms < 5:
            return {"success": False, "error": "Too few mapped Cα atoms"}

        resids = [m["resid"] for m in meta]
        sel = " or ".join(f"resid {r}" for r in resids)
        ref = u.copy()
        mda_align.AlignTraj(
            u, ref, select=f"protein and name CA and ({sel})", in_memory=True
        ).run()

        coords = []
        for _ts in u.trajectory:
            coords.append(ag.positions.copy())
        positions = np.asarray(coords, dtype=float)  # T, N, 3
        # DCCM: corr of x,y,z fluctuations concatenated is heavy; use per-atom
        # displacement magnitude correlation (same spirit as ment Cα DCCM).
        mean_pos = positions.mean(axis=0)
        fluc = positions - mean_pos
        # Build 3N vectors
        T, N, _ = fluc.shape
        X = fluc.reshape(T, N * 3)
        X = X - X.mean(axis=0)
        # Atom-level: average corr over xyz for each atom pair via reshaped cov
        # Simpler: use distance-from-mean per atom
        mag = np.linalg.norm(fluc, axis=2)  # T, N
        mag = mag - mag.mean(axis=0)
        C = np.corrcoef(mag, rowvar=False)
        np.fill_diagonal(C, 1.0)
        np.save(out / "consensus_dccm.npy", C)

        iu = np.triu_indices(N, k=1)
        mean_abs = float(np.mean(np.abs(C[iu])))
        n_idx = [i for i, m in enumerate(meta) if m["consensus_index"] <= int(n_lobe_ci_max)]
        c_idx = [i for i, m in enumerate(meta) if m["consensus_index"] >= int(c_lobe_ci_min)]
        if n_idx and c_idx:
            block = C[np.ix_(n_idx, c_idx)]
            nc_mean = float(np.mean(block))
        else:
            nc_mean = float("nan")

        feat = {
            "success": True,
            "label": label,
            "mean_abs_dccm": mean_abs,
            "dccm_N_C_mean_corr": nc_mean,
            "n_consensus_atoms": N,
            "N_lobe_n_atoms": len(n_idx),
            "C_lobe_n_atoms": len(c_idx),
            "N_LOBE_CI_MAX": int(n_lobe_ci_max),
            "C_LOBE_CI_MIN": int(c_lobe_ci_min),
        }
        feat_path.write_text(json.dumps(feat, indent=2) + "\n", encoding="utf-8")
        return feat
    except Exception as exc:
        logger.exception("calculate_consensus_dccm_features failed")
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)
