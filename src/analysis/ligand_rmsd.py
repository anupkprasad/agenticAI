"""Ligand RMSD after protein alignment — standard holo MD metric."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import align, rms
    import numpy as np

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@tool
def calculate_ligand_rmsd(
    topology_file: str,
    trajectory_file: str,
    protein_selection: str = "protein and name CA",
    ligand_selection: str = "resname ATP ADP AMP GTP GDP LIG INH",
    reference_frame: int = 0,
    output_file: str = "ligand_rmsd.dat",
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate ligand RMSD over the trajectory after aligning on the protein.

    Aligns each frame to the reference using ``protein_selection``, then
    measures RMSD of ``ligand_selection``.
    """
    if not HAS_DEPS:
        return {"success": False, "error": "MDAnalysis and numpy required"}

    top = Path(topology_file)
    traj = Path(trajectory_file)
    if not top.is_file() or not traj.is_file():
        return {"success": False, "error": f"Missing topology/trajectory: {top}, {traj}"}

    try:
        u = mda.Universe(str(top), str(traj))
        protein = u.select_atoms(protein_selection)
        ligand = u.select_atoms(ligand_selection)
        if len(protein) == 0:
            return {"success": False, "error": f"Empty protein selection: {protein_selection}"}
        if len(ligand) == 0:
            return {"success": False, "error": f"Empty ligand selection: {ligand_selection}"}

        align.AlignTraj(u, u, select=protein_selection, in_memory=True).run()

        ref = mda.Universe(str(top), str(traj))
        ref.trajectory[reference_frame]
        ref_lig = ref.select_atoms(ligand_selection).positions.copy()

        times = []
        values = []
        ligand = u.select_atoms(ligand_selection)
        for ts in u.trajectory:
            val = rms.rmsd(ligand.positions, ref_lig, superposition=False)
            times.append(float(ts.time))
            values.append(float(val))

        arr = np.asarray(values, dtype=float)
        if working_dir and not Path(output_file).is_absolute():
            out = Path(working_dir) / output_file
        else:
            out = Path(output_file)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as fh:
            fh.write("# Time(ns)\tLigand_RMSD(Angstrom)\n")
            for t, r in zip(times, arr):
                fh.write(f"{float(t) / 1000.0:.4f}\t{r:.4f}\n")

        stats = {
            "n_frames": int(arr.size),
            "mean_rmsd_angstrom": float(arr.mean()),
            "std_rmsd_angstrom": float(arr.std()),
            "min_rmsd_angstrom": float(arr.min()),
            "max_rmsd_angstrom": float(arr.max()),
            "protein_selection": protein_selection,
            "ligand_selection": ligand_selection,
            "output_file": str(out),
        }
        if working_dir:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Ligand_RMSD",
                statistics=stats,
                files={"data": str(out)},
            )
        return {"success": True, **stats}
    except Exception as exc:
        logger.exception("calculate_ligand_rmsd failed")
        return {"success": False, "error": str(exc)}
