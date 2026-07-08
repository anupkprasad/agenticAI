"""
Batch orchestrator for trajectory metrics.

Groups plan steps into RAW and ALIGNED passes so each pass loads the
trajectory once.  STREAMING metrics in the same pass share a single
``for ts in u.trajectory`` loop when their frame intervals are compatible.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .metric_registry import (
    TrajectoryExecutionMode,
    TrajectoryPassKind,
    get_metric_spec,
    is_batchable_trajectory_tool,
    resolve_effective_pass_kind,
)
from .trajectory_compute import compute_metric_from_session, run_fused_raw_streaming_batch
from .trajectory_session import TrajectorySession

logger = logging.getLogger(__name__)

# Plot / file-only tools never participate in trajectory batching.
_NON_TRAJECTORY_PREFIXES = ("plot_", "collect_", "cluster_", "run_combined_")


@dataclass
class TrajectoryBatchGroup:
    """A set of calculation steps sharing one trajectory pass."""

    pass_kind: TrajectoryPassKind
    step_indices: List[int] = field(default_factory=list)
    tool_names: List[str] = field(default_factory=list)
    execution_modes: List[TrajectoryExecutionMode] = field(default_factory=list)

    @property
    def has_streaming(self) -> bool:
        return any(m == TrajectoryExecutionMode.STREAMING for m in self.execution_modes)

    @property
    def can_fuse_streaming_loop(self) -> bool:
        return (
            self.pass_kind == TrajectoryPassKind.RAW
            and self.has_streaming
            and len(self.step_indices) > 1
        )


def is_trajectory_calculation_step(tool_name: str) -> bool:
    if not tool_name or tool_name.startswith(_NON_TRAJECTORY_PREFIXES):
        return False
    spec = get_metric_spec(tool_name)
    if spec is None:
        return False
    return spec.is_trajectory_metric


def partition_plan_into_pass_groups(
    steps: Sequence[Any],
) -> Tuple[List[TrajectoryBatchGroup], List[int]]:
    """
    Split plan steps into trajectory pass groups and non-trajectory indices.

    Consecutive trajectory-calculation steps with the same ``TrajectoryPassKind``
    form one group.  Plot steps and external tools break batching.
    """
    groups: List[TrajectoryBatchGroup] = []
    non_trajectory: List[int] = []
    current: Optional[TrajectoryBatchGroup] = None

    for idx, step in enumerate(steps):
        tool_name = getattr(step, "tool_name", "") or ""
        spec = get_metric_spec(tool_name)

        if spec is None or not spec.is_trajectory_metric:
            non_trajectory.append(idx)
            current = None
            continue

        if current is None or current.pass_kind != spec.pass_kind:
            current = TrajectoryBatchGroup(
                pass_kind=spec.pass_kind,
                step_indices=[idx],
                tool_names=[tool_name],
                execution_modes=[spec.execution_mode],
            )
            groups.append(current)
        else:
            current.step_indices.append(idx)
            current.tool_names.append(tool_name)
            current.execution_modes.append(spec.execution_mode)

    return groups, non_trajectory


def estimate_pass_count(steps: Sequence[Any]) -> Dict[str, int]:
    """Rough savings estimate: passes vs naive one-load-per-tool."""
    groups, _ = partition_plan_into_pass_groups(steps)
    traj_steps = sum(
        1 for s in steps if is_trajectory_calculation_step(getattr(s, "tool_name", "") or "")
    )
    return {
        "trajectory_calc_steps": traj_steps,
        "pass_groups": len(groups),
        "estimated_universe_loads_naive": traj_steps,
        "estimated_universe_loads_batched": len(groups),
    }


def build_session_from_params(
    topology_file: str,
    trajectory_file: str,
    working_dir: Optional[str],
    *,
    reference_frame: int = 0,
    align_selection: str = "protein and name CA",
) -> TrajectorySession:
    return TrajectorySession(
        topology_file,
        trajectory_file,
        working_dir=working_dir,
        reference_frame=reference_frame,
        default_align_selection=align_selection,
    )


def summarize_batch_plan(steps: Sequence[Any]) -> str:
    """Human-readable summary for logs."""
    groups, _ = partition_plan_into_pass_groups(steps)
    if not groups:
        return "No trajectory batch groups (plot-only or external tools)."
    lines = ["Trajectory batch plan:"]
    for i, g in enumerate(groups, 1):
        fuse = " [fused streaming loop]" if g.can_fuse_streaming_loop else ""
        lines.append(
            f"  Pass {i} ({g.pass_kind.value}): {', '.join(g.tool_names)}{fuse}"
        )
    est = estimate_pass_count(steps)
    lines.append(
        f"  Loads: {est['estimated_universe_loads_naive']} naive → "
        f"{est['estimated_universe_loads_batched']} batched"
    )
    return "\n".join(lines)


def _collect_trajectory_steps(
    steps: Sequence[Any],
    prepared_params: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[tuple]:
    """Return (index, tool_name, params) for batchable trajectory calc steps."""
    collected = []
    for idx, step in enumerate(steps):
        tool_name = getattr(step, "tool_name", "") or ""
        spec = get_metric_spec(tool_name)
        if spec is None or not spec.is_trajectory_metric:
            continue
        if prepared_params and idx in prepared_params:
            params = dict(prepared_params[idx])
        else:
            params = dict(getattr(step, "tool_params", None) or {})
        collected.append((idx, tool_name, params))
    return collected


def run_plan_trajectory_batches(
    steps: Sequence[Any],
    *,
    topology_file: str,
    trajectory_file: str,
    working_dir: Optional[str],
    reference_frame: int = 0,
    default_align_selection: str = "protein and name CA",
    prepared_params: Optional[Dict[int, Dict[str, Any]]] = None,
) -> Dict[int, Dict[str, Any]]:
    """
    Execute all trajectory metrics in minimal passes (global batching).

    Returns a map of plan step index → tool result dict.
    """
    import os

    traj_steps = _collect_trajectory_steps(steps, prepared_params)
    if not traj_steps:
        return {}

    aligned: List[tuple] = []
    raw_streaming: List[tuple] = []
    raw_other: List[tuple] = []

    for item in traj_steps:
        idx, tool_name, params = item
        pass_kind = resolve_effective_pass_kind(tool_name, params)
        spec = get_metric_spec(tool_name)
        if pass_kind == TrajectoryPassKind.ALIGNED:
            aligned.append(item)
        elif spec and spec.execution_mode == TrajectoryExecutionMode.STREAMING:
            raw_streaming.append(item)
        else:
            raw_other.append(item)

    if not aligned and not raw_streaming and not raw_other:
        return {}

    session = build_session_from_params(
        topology_file,
        trajectory_file,
        working_dir,
        reference_frame=reference_frame,
        align_selection=default_align_selection,
    )

    results: Dict[int, Dict[str, Any]] = {}
    original_dir = os.getcwd()
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            os.chdir(working_dir)

        if aligned:
            logger.info(
                "Trajectory batch: ALIGNED pass (%d metrics): %s",
                len(aligned),
                ", ".join(t for _, t, _ in aligned),
            )
            session.record_pass("aligned_batch", n_metrics=len(aligned))
            for idx, tool_name, params in aligned:
                try:
                    results[idx] = compute_metric_from_session(
                        tool_name,
                        session,
                        TrajectoryPassKind.ALIGNED,
                        topology_file=topology_file,
                        trajectory_file=trajectory_file,
                        working_dir=working_dir,
                        params=params,
                    )
                except Exception as exc:
                    logger.exception("Aligned batch metric %s failed: %s", tool_name, exc)
                    results[idx] = {"success": False, "error": str(exc)}

        if raw_streaming:
            logger.info(
                "Trajectory batch: RAW streaming pass (%d metrics): %s",
                len(raw_streaming),
                ", ".join(t for _, t, _ in raw_streaming),
            )
            fused = run_fused_raw_streaming_batch(
                session,
                raw_streaming,
                topology_file=topology_file,
                trajectory_file=trajectory_file,
                working_dir=working_dir,
            )
            results.update(fused)

        if raw_other:
            logger.info(
                "Trajectory batch: RAW shared-universe pass (%d metrics): %s",
                len(raw_other),
                ", ".join(t for _, t, _ in raw_other),
            )
            session.record_pass("raw_batch", n_metrics=len(raw_other))
            for idx, tool_name, params in raw_other:
                try:
                    results[idx] = compute_metric_from_session(
                        tool_name,
                        session,
                        TrajectoryPassKind.RAW,
                        topology_file=topology_file,
                        trajectory_file=trajectory_file,
                        working_dir=working_dir,
                        params=params,
                    )
                except Exception as exc:
                    logger.exception("Raw batch metric %s failed: %s", tool_name, exc)
                    results[idx] = {"success": False, "error": str(exc)}

        logger.info(
            "Trajectory batch complete: %s",
            session.stats,
        )

        if working_dir:
            try:
                from .summary_logger import append_trajectory_batch_summary

                append_trajectory_batch_summary(
                    working_dir,
                    session.stats,
                    aligned_metrics=[t for _, t, _ in aligned],
                    raw_streaming_metrics=[t for _, t, _ in raw_streaming],
                    raw_batch_metrics=[t for _, t, _ in raw_other],
                    step_indices=[i for i, _, _ in traj_steps],
                    topology_file=topology_file,
                    trajectory_file=trajectory_file,
                )
            except Exception as exc:
                logger.warning("Failed to log trajectory batch summary: %s", exc)
    finally:
        if working_dir:
            os.chdir(original_dir)
        session.close()

    return results
