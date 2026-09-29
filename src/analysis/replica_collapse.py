"""Detect when multi-replicate analysis wrote identical science products."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.analysis.replicate_paths import (
    analysis_rep_dir,
    iter_rep_ids,
    normalize_rep_num,
    resolve_production_trajectory,
    uses_nested_reps,
)

logger = logging.getLogger(__name__)

SCIENCE_RELATIVE_PATHS: Tuple[str, ...] = (
    "ligand_pocket_distance.csv",
    "consensus_rmsf/per_residue_rmsf.csv",
    "consensus_DCCM/consensus_dccm.npy",
    "consensus_dihedrals/dihedral_sincos.npy",
    "consensus_PCA/pca_projections.npy",
)


def file_md5(path: Path, nbytes: int = 0) -> Optional[str]:
    if not path.is_file():
        return None
    h = hashlib.md5()
    with path.open("rb") as fh:
        if nbytes > 0:
            h.update(fh.read(nbytes))
        else:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def same_inode(a: Path, b: Path) -> bool:
    try:
        sa, sb = a.stat(), b.stat()
        return (sa.st_dev, sa.st_ino) == (sb.st_dev, sb.st_ino)
    except OSError:
        return False


def trajectories_are_distinct(sim_dir: Path | str, rep_num: int) -> Tuple[bool, List[str]]:
    """True when at least two replica xtcs are different files."""
    sim = Path(sim_dir)
    nested = uses_nested_reps(rep_num)
    paths: List[Path] = []
    for rid in iter_rep_ids(rep_num):
        hpc = sim / "hpc" / rid if nested else sim / "hpc"
        traj = resolve_production_trajectory(hpc)
        if traj is not None:
            paths.append(traj.resolve())
    if len(paths) < 2:
        return False, [str(p) for p in paths]
    distinct = True
    for i in range(1, len(paths)):
        if paths[i] == paths[0] or same_inode(paths[0], paths[i]):
            distinct = False
            break
    return distinct, [str(p) for p in paths]


def replica_science_collapsed(
    sim_dir: Path | str,
    rep_num: int,
    *,
    relative_paths: Sequence[str] = SCIENCE_RELATIVE_PATHS,
) -> Dict[str, Any]:
    """Compare per-rep science files. Collapse = same bytes, different trajectories."""
    n = normalize_rep_num(rep_num)
    sim = Path(sim_dir)
    nested = uses_nested_reps(n)
    if n < 2:
        return {"collapsed": False, "reason": "single_replica", "matches": []}

    matches: List[str] = []
    compared = 0
    for rel in relative_paths:
        hashes: List[Optional[str]] = []
        present = 0
        for rid in iter_rep_ids(n):
            p = analysis_rep_dir(sim, rid, nested=nested) / rel
            digest = file_md5(p)
            hashes.append(digest)
            if digest:
                present += 1
        if present < 2:
            continue
        compared += 1
        first = next(h for h in hashes if h)
        if all(h == first for h in hashes if h):
            matches.append(rel)

    distinct_traj, trajs = trajectories_are_distinct(sim, n)
    collapsed = bool(matches) and distinct_traj
    return {
        "collapsed": collapsed,
        "identical_products": matches,
        "n_compared": compared,
        "trajectories_distinct": distinct_traj,
        "trajectories": trajs,
        "reason": (
            "identical_science_on_distinct_trajectories"
            if collapsed
            else (
                "identical_science_same_trajectory"
                if matches and not distinct_traj
                else "ok"
            )
        ),
    }
