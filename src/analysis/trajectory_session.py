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


def _clip_truncated_trajectory(universe: Any) -> Any:
    """Cap n_frames when the XTC is truncated (mdrun XTC error / disk full).

    MDAnalysis estimates ``n_frames`` from file size after ``seek failed``.
    A 77 ns / 100 ps production then looks like ~15k frames and AlignTraj
    ``in_memory=True`` tries to allocate tens of GB.
    """
    reader = universe.trajectory
    claimed = len(reader)
    if claimed <= 0:
        return universe
    try:
        reader[claimed - 1]
        return universe
    except Exception:
        logger.info(
            "TrajectorySession: last-frame seek failed (claimed n_frames=%d) "
            "— counting readable frames",
            claimed,
        )

    readable = 0
    last_time = None
    try:
        for ts in reader:
            readable += 1
            last_time = getattr(ts, "time", None)
    except Exception as exc:
        logger.warning(
            "TrajectorySession: stopped counting frames at %d (%s: %s)",
            readable,
            type(exc).__name__,
            exc,
        )
    if readable <= 0:
        raise RuntimeError(
            f"Trajectory has no readable frames: {getattr(universe, 'filename', '')}"
        )
    if readable < claimed:
        logger.warning(
            "TrajectorySession: truncated XTC — using %d readable frames "
            "(MDA claimed %d, last time %.1f ps). Loading those frames into memory.",
            readable,
            claimed,
            float(last_time) if last_time is not None else -1.0,
        )
        universe.transfer_to_memory(start=0, stop=readable)
    return universe


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
        self._chain_map: Any = False  # False = not loaded yet; None = missing
        self._stats: Dict[str, Any] = {
            "universe_loads": 0,
            "align_runs": 0,
            "passes": [],
        }

    @property
    def chain_map(self) -> Any:
        """PDB chain → trajectory resindex map, loaded once per session."""
        if self._chain_map is False:
            from .chain_residue_map import ensure_chain_residue_map

            self._chain_map = ensure_chain_residue_map(
                working_dir=self.working_dir,
                topology_file=self.topology_file,
            )
        return self._chain_map

    def translate_selection(self, selection: Optional[str]) -> Optional[str]:
        if not selection or not isinstance(selection, str):
            return selection
        from .chain_residue_map import translate_selection

        return translate_selection(selection, self.chain_map)

    def translate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        from .chain_residue_map import params_need_chain_map, translate_selection_params

        if not params_need_chain_map(params):
            return dict(params)
        return translate_selection_params(params, self.chain_map)

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
        return _clip_truncated_trajectory(u)

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
        sel = self.translate_selection(sel) or sel
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
        self._chain_map = False


def create_session(
    topology_file: str,
    trajectory_file: str,
    **kwargs: Any,
) -> TrajectorySession:
    return TrajectorySession(topology_file, trajectory_file, **kwargs)
