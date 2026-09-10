"""Native contacts and backbone dihedral helpers for general MD analysis."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import distances
    import numpy as np

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@tool
def calculate_native_contacts(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    cutoff_angstrom: float = 8.0,
    reference_frame: int = 0,
    output_file: str = "native_contacts.dat",
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fraction of native contacts retained vs a reference frame.

    Builds a contact map on ``reference_frame`` (pairs of selected atoms within
    ``cutoff_angstrom``) and reports the fraction present in each frame.
    """
    if not HAS_DEPS:
        return {"success": False, "error": "MDAnalysis and numpy required"}
    top, traj = Path(topology_file), Path(trajectory_file)
    if not top.is_file() or not traj.is_file():
        return {"success": False, "error": f"Missing files: {top}, {traj}"}

    try:
        u = mda.Universe(str(top), str(traj))
        atoms = u.select_atoms(selection)
        if len(atoms) < 2:
            return {"success": False, "error": f"Need ≥2 atoms for selection: {selection}"}

        u.trajectory[reference_frame]
        d0 = distances.self_distance_array(atoms.positions)
        # self_distance_array returns condensed vector; rebuild pair mask
        n = len(atoms)
        native = d0 < float(cutoff_angstrom)
        n_native = int(np.count_nonzero(native))
        if n_native == 0:
            return {"success": False, "error": "No native contacts at reference frame"}

        times, fracs = [], []
        for ts in u.trajectory:
            d = distances.self_distance_array(atoms.positions)
            present = np.count_nonzero((d < float(cutoff_angstrom)) & native)
            times.append(float(ts.time))
            fracs.append(float(present) / float(n_native))

        arr = np.asarray(fracs, dtype=float)
        out = Path(working_dir or ".") / output_file if working_dir and not Path(output_file).is_absolute() else Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("# Time(ps)\tNativeContactFraction\n")
            for t, f in zip(times, arr):
                fh.write(f"{t:.4f}\t{f:.6f}\n")

        stats = {
            "n_frames": int(arr.size),
            "n_native_pairs": n_native,
            "cutoff_angstrom": float(cutoff_angstrom),
            "mean_fraction": float(arr.mean()),
            "final_fraction": float(arr[-1]),
            "output_file": str(out),
        }
        if working_dir:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Native_Contacts",
                statistics=stats,
                files={"data": str(out)},
            )
        return {"success": True, **stats}
    except Exception as exc:
        logger.exception("calculate_native_contacts failed")
        return {"success": False, "error": str(exc)}


@tool
def calculate_backbone_dihedrals(
    topology_file: str,
    trajectory_file: str,
    residue_selection: str = "protein",
    max_residues: int = 50,
    output_file: str = "backbone_dihedrals.dat",
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Write backbone φ/ψ dihedral time series for up to ``max_residues``.

    Useful for loop/hinge dynamics in family comparisons. Output columns:
    time_ps, resid, phi_deg, psi_deg (one row per residue per frame sample).
    Frames are stride-sampled to keep files manageable (every max(1, n_frames//200)).
    """
    if not HAS_DEPS:
        return {"success": False, "error": "MDAnalysis and numpy required"}
    try:
        from MDAnalysis.analysis.dihedrals import Ramachandran
    except Exception as exc:
        return {"success": False, "error": f"Ramachandran analysis unavailable: {exc}"}

    top, traj = Path(topology_file), Path(trajectory_file)
    if not top.is_file() or not traj.is_file():
        return {"success": False, "error": f"Missing files: {top}, {traj}"}

    try:
        u = mda.Universe(str(top), str(traj))
        sel = u.select_atoms(residue_selection)
        if len(sel.residues) == 0:
            return {"success": False, "error": "No residues selected"}

        # Cap residues by restricting selection when possible
        rama = Ramachandran(sel).run()
        angles = rama.results.angles  # (n_frames, n_residues, 2)
        if angles.shape[1] > int(max_residues):
            angles = angles[:, : int(max_residues), :]
        n_frames = angles.shape[0]
        stride = max(1, n_frames // 200)
        out = Path(working_dir or ".") / output_file if working_dir and not Path(output_file).is_absolute() else Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("# frame\ttime_ps\tres_index\tphi_deg\tpsi_deg\n")
            for fi in range(0, n_frames, stride):
                u.trajectory[fi]
                t = float(u.trajectory.time)
                for ri in range(angles.shape[1]):
                    phi, psi = angles[fi, ri]
                    fh.write(f"{fi}\t{t:.3f}\t{ri}\t{float(phi):.2f}\t{float(psi):.2f}\n")

        stats = {
            "n_frames": n_frames,
            "n_residues": int(angles.shape[1]),
            "stride": stride,
            "output_file": str(out),
        }
        if working_dir:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Backbone_Dihedrals",
                statistics=stats,
                files={"data": str(out)},
            )
        return {"success": True, **stats}
    except Exception as exc:
        logger.exception("calculate_backbone_dihedrals failed")
        return {"success": False, "error": str(exc)}
