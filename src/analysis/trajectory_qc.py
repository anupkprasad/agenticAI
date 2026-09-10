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
) -> Dict[str, Any]:
    """
    Quick trajectory QC: n_frames, dt, box lengths, protein CA RMSD drift.

    Use early in per-sim analysis to catch truncated or unstable runs before
    spending tokens on heavy metrics.
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
