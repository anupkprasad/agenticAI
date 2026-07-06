"""
Shared MDAnalysis trajectory session for batched metrics.

MDAnalysis ``Universe`` does not load all frames into RAM — the cost is
``for ts in u.trajectory``.  This module keeps at most:

  - one RAW Universe (no superposition)
  - one ALIGNED Universe per align selection (``AlignTraj`` run once)

Downstream calculators receive a session instead of reopening the trajectory.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Tuple

from .metric_registry import TrajectoryPassKind

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import align

    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    mda = None  # type: ignore
    align = None  # type: ignore


class TrajectorySession:
    """Lazy-loaded trajectory context with separate RAW and ALIGNED passes."""

    def __init__(
        self,
        topology_file: str,
        trajectory_file: str,
        *,
        working_dir: Optional[str] = None,
        reference_frame: int = 0,
        default_align_selection: str = "protein and name CA",
    ) -> None:
        self.topology_file = topology_file
        self.trajectory_file = trajectory_file
        self.working_dir = working_dir
        self.reference_frame = reference_frame
        self.default_align_selection = default_align_selection

        self._raw_universe: Any = None
        self._aligned_cache: Dict[str, Any] = {}
        self._stats: Dict[str, Any] = {
            "universe_loads": 0,
            "align_runs": 0,
            "passes": [],
        }

    @property
    def stats(self) -> Dict[str, Any]:
        return dict(self._stats)

    def _load_universe(self) -> Any:
        if not HAS_MDA:
            raise RuntimeError("MDAnalysis is required for trajectory batching")
        logger.info(
            "TrajectorySession: loading Universe (%s + %s)",
            self.topology_file,
            self.trajectory_file,
        )
        u = mda.Universe(self.topology_file, self.trajectory_file)
        self._stats["universe_loads"] += 1
        return u

    @property
    def raw_universe(self) -> Any:
        if self._raw_universe is None:
            self._raw_universe = self._load_universe()
        return self._raw_universe

    @property
    def n_frames(self) -> int:
        return len(self.raw_universe.trajectory)

    def get_universe(
        self,
        pass_kind: TrajectoryPassKind,
        *,
        align_selection: Optional[str] = None,
        align_trajectory: bool = True,
    ) -> Any:
        """Return the Universe appropriate for the requested pass."""
        if pass_kind in (TrajectoryPassKind.RAW, TrajectoryPassKind.INTERNAL):
            return self.raw_universe
        if not align_trajectory:
            return self.raw_universe
        return self.aligned_universe(align_selection=align_selection)

    def aligned_universe(self, *, align_selection: Optional[str] = None) -> Any:
        """Return an in-memory aligned copy; computed once per selection string."""
        sel = (align_selection or self.default_align_selection).strip()
        if sel in self._aligned_cache:
            return self._aligned_cache[sel]

        u = self.raw_universe.copy()
        ref = self.raw_universe.copy()
        ref_idx = max(0, min(int(self.reference_frame), self.n_frames - 1))
        ref.trajectory[ref_idx]

        logger.info(
            "TrajectorySession: AlignTraj (ref=%d, select=%r, n_frames=%d)",
            ref_idx,
            sel,
            self.n_frames,
        )
        align.AlignTraj(u, ref, select=sel, in_memory=True).run()
        self._aligned_cache[sel] = u
        self._stats["align_runs"] += 1
        self._stats["passes"].append({"kind": "aligned", "selection": sel})
        return u

    def record_pass(self, kind: str, **meta: Any) -> None:
        entry = {"kind": kind, **meta}
        self._stats["passes"].append(entry)
        logger.debug("TrajectorySession pass recorded: %s", entry)

    def close(self) -> None:
        """Release references (Universe holds file handles until GC)."""
        self._raw_universe = None
        self._aligned_cache.clear()


def create_session(
    topology_file: str,
    trajectory_file: str,
    **kwargs: Any,
) -> TrajectorySession:
    return TrajectorySession(topology_file, trajectory_file, **kwargs)
