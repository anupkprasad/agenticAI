"""Resolve topology/trajectory for one HPC slot — never pick the first replica silently."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def resolve_topology_trajectory(
    topology_file: str = "",
    trajectory_file: str = "",
    *,
    sim_directory: Optional[str] = None,
    hpc_dir: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Return absolute ``(topology, trajectory)`` for one replicate.

    Order:
      1. Use both caller paths when they exist.
      2. If ``hpc_dir`` is set, resolve production files there.
      3. If only one nested ``hpc/repXX`` (or a flat ``hpc/``) exists, search it.
      4. If several replica directories exist and ``hpc_dir`` was omitted, refuse
         to guess — callers must bind a slot. The old first-hit search made
         every replica analyze ``rep01``.
    """
    from src.analysis.replicate_paths import (
        discover_hpc_rep_dirs,
        resolve_production_topology,
        resolve_production_trajectory,
    )

    top = _existing_file(topology_file)
    traj = _existing_file(trajectory_file)
    if top and traj:
        return top, traj

    if hpc_dir:
        slot = Path(hpc_dir)
        if slot.is_dir():
            found_top = resolve_production_topology(slot)
            found_traj = resolve_production_trajectory(slot)
            return (
                top or (str(found_top.resolve()) if found_top else None),
                traj or (str(found_traj.resolve()) if found_traj else None),
            )

    if not sim_directory:
        return top, traj

    roots = discover_hpc_rep_dirs(sim_directory)
    if len(roots) > 1:
        logger.error(
            "traj_resolve: %d hpc replica dirs under %s but hpc_dir was not set — "
            "refusing first-hit fallback",
            len(roots),
            sim_directory,
        )
        return top, traj
    if len(roots) == 1:
        found_top = resolve_production_topology(roots[0])
        found_traj = resolve_production_trajectory(roots[0])
        return (
            top or (str(found_top.resolve()) if found_top else None),
            traj or (str(found_traj.resolve()) if found_traj else None),
        )

    from src.analysis.combined_analysis import _find_sim_traj_topology

    found = _find_sim_traj_topology(str(sim_directory), hpc_dir=hpc_dir)
    return top or found[0], traj or found[1]


def _existing_file(path: str) -> Optional[str]:
    if not path:
        return None
    p = Path(path)
    if p.is_file() and p.stat().st_size > 0:
        return str(p.resolve())
    return None
