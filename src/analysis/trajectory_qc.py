"""Trajectory quality-control summary for MD campaigns."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import rms
    import numpy as np

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


@tool
def run_trajectory_qc(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    output_json: str = "trajectory_qc.json",
    working_dir: Optional[str] = None,
    ligand_selection: str = "",
    reference_pdb: str = "",
) -> Dict[str, Any]:
    """
    Trajectory quality checks: length, box, Cα RMSD drift, optional ligand
    RMSD to the first (or crystal) frame, and a simple Ramachandran outlier
    fraction. Replica-collapse (identical products on distinct trajectories)
    is a separate gate.
    """
    if not HAS_DEPS:
        return {"success": False, "error": "MDAnalysis and numpy required"}

    top = Path(topology_file)
    traj = Path(trajectory_file)
    if not top.is_file() or not traj.is_file():
        return {"success": False, "error": f"Missing files: {top}, {traj}"}

    try:
        u = mda.Universe(str(top), str(traj))
        n_frames = len(u.trajectory)
        times = [float(ts.time) for ts in u.trajectory]
        dt = float(times[1] - times[0]) if n_frames > 1 else 0.0
        u.trajectory[-1]
        box = u.dimensions
        box_abc = [float(x) for x in (box[:3] if box is not None else [0, 0, 0])]

        R = rms.RMSD(u, select=selection, ref_frame=0)
        R.run()
        rmsd = R.results.rmsd[:, 2]
        # PBC jump: protein COM displacement vs half-box
        prot = u.select_atoms("protein")
        com0 = prot.center_of_mass() if len(prot) else None
        u.trajectory[-1]
        com1 = prot.center_of_mass() if len(prot) else None
        com_jump = None
        pbc_suspect = False
        if com0 is not None and com1 is not None and box_abc[0] > 0:
            com_jump = float(np.linalg.norm(np.asarray(com1) - np.asarray(com0)))
            pbc_suspect = com_jump > 0.5 * min(box_abc)

        rama_outlier_frac = None
        try:
            from MDAnalysis.analysis.dihedrals import Ramachandran

            rama = Ramachandran(u.select_atoms("protein")).run()
            angles = np.asarray(rama.results.angles)
            # Crude disallowed: |φ|>150 and |ψ|<30 (left-handed sparse region)
            if angles.size:
                phi = angles[..., 0]
                psi = angles[..., 1]
                bad = (np.abs(phi) > 150.0) & (np.abs(psi) < 30.0)
                rama_outlier_frac = float(np.mean(bad))
        except Exception:
            rama_outlier_frac = None

        ligand_rmsd_mean = None
        if ligand_selection:
            try:
                ref = mda.Universe(str(reference_pdb)) if reference_pdb and Path(reference_pdb).is_file() else u
                lig_sel = ligand_selection
                Rlig = rms.RMSD(u, ref, select=lig_sel, ref_frame=0)
                Rlig.run()
                ligand_rmsd_mean = float(np.mean(Rlig.results.rmsd[:, 2]))
            except Exception as lig_exc:
                logger.debug("ligand RMSD in QC skipped: %s", lig_exc)

        result = {
            "success": True,
            "n_frames": n_frames,
            "n_atoms": int(u.atoms.n_atoms),
            "time_first_ps": times[0] if times else None,
            "time_last_ps": times[-1] if times else None,
            "dt_ps": dt,
            "box_A": box_abc,
            "rmsd_selection": selection,
            "rmsd_mean_A": float(np.mean(rmsd)),
            "rmsd_final_A": float(rmsd[-1]),
            "rmsd_max_A": float(np.max(rmsd)),
            "protein_com_jump_A": com_jump,
            "pbc_unwrap_suspect": pbc_suspect,
            "ramachandran_outlier_fraction": rama_outlier_frac,
            "ligand_rmsd_mean_A": ligand_rmsd_mean,
        }
        out = Path(working_dir or ".") / output_json if working_dir and not Path(output_json).is_absolute() else Path(output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        result["output_json"] = str(out)
        if working_dir:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Trajectory_QC",
                statistics={k: result[k] for k in ("n_frames", "dt_ps", "rmsd_mean_A", "rmsd_final_A") if k in result},
                files={"json": str(out)},
            )
        return result
    except Exception as exc:
        logger.exception("run_trajectory_qc failed")
        return {"success": False, "error": str(exc)}
