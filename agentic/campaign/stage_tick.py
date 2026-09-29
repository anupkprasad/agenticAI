"""Forward-only pipeline ticks for family / multi-sim MD.

Campaign order (one DAG):

    pre_combined → preprocess → setup → hpc → analysis → reporter → post_combined

Once a stage has succeeded (state or disk), the supervisor must tick **forward**.
Retries stay on the *current* failed stage. Planner / HITL can be consulted on
error; they do not rewind completed stages.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Internal supervisor names (see get_agent_execution_order).
PER_SIM_STAGES: Tuple[str, ...] = (
    "preprocessing",
    "simsetup",
    "hpc",
    "analysis",
    "reporter",
)

CLI_TO_INTERNAL = {
    "preprocess": "preprocessing",
    "preprocessing": "preprocessing",
    "simsetup": "simsetup",
    "setup": "simsetup",
    "hpc": "hpc",
    "hpcjob": "hpc",
    "analysis": "analysis",
    "reporter": "reporter",
}

INTERNAL_TO_NODE = {
    "preprocessing": "preprocess",
    "simsetup": "setup",
    "hpc": "hpc",
    "analysis": "analysis",
    "reporter": "reporter",
}


def normalize_stage(name: str) -> str:
    return CLI_TO_INTERNAL.get(str(name).strip().lower(), str(name).strip().lower())


def _sim_dir(state: Dict[str, Any]) -> Optional[Path]:
    wd = state.get("working_directory")
    if not wd:
        return None
    p = Path(wd)
    return p if p.is_dir() else p


def preprocess_done_on_disk(sim_dir: Path | str) -> bool:
    root = Path(sim_dir) / "preprocess"
    if not root.is_dir():
        return False
    return any(
        (root / name).is_file()
        for name in ("protein_h.pdb", "protein.pdb", "raw.pdb")
    )


def setup_done_on_disk(sim_dir: Path | str) -> bool:
    root = Path(sim_dir) / "simsetup"
    if not root.is_dir():
        return False
    return (
        (root / "topol.top").is_file()
        or (root / "system.gro").is_file()
        or (root / "solvated.gro").is_file()
        or any(root.glob("*.top"))
    )


def hpc_done_on_disk(sim_dir: Path | str) -> bool:
    from src.analysis.replicate_paths import (
        discover_hpc_rep_dirs,
        resolve_production_trajectory,
    )

    roots = discover_hpc_rep_dirs(sim_dir)
    if not roots:
        flat = Path(sim_dir) / "hpc"
        roots = [flat] if flat.is_dir() else []
    if not roots:
        return False
    for hpc in roots:
        traj = resolve_production_trajectory(hpc)
        tpr = hpc / "md.tpr"
        if traj is None or not tpr.is_file():
            return False
    return True


def analysis_done_on_disk(sim_dir: Path | str) -> bool:
    from agentic.multi_sim_progress import per_sim_analysis_done_on_disk

    return bool(per_sim_analysis_done_on_disk(str(sim_dir)))


def reporter_done_on_disk(sim_dir: Path | str) -> bool:
    from agentic.multi_sim_progress import per_sim_reporter_done_on_disk

    return bool(per_sim_reporter_done_on_disk(str(sim_dir)))


def stage_done_on_disk(sim_dir: Path | str, stage: str) -> bool:
    key = normalize_stage(stage)
    if key == "preprocessing":
        return preprocess_done_on_disk(sim_dir)
    if key == "simsetup":
        return setup_done_on_disk(sim_dir)
    if key == "hpc":
        return hpc_done_on_disk(sim_dir)
    if key == "analysis":
        return analysis_done_on_disk(sim_dir)
    if key == "reporter":
        return reporter_done_on_disk(sim_dir)
    return False


def restore_stage_artifacts(state: Dict[str, Any]) -> Dict[str, Any]:
    """Fill missing state pointers from disk so later ticks do not rewind."""
    sim = _sim_dir(state)
    if sim is None:
        return state
    if not state.get("cleaned_pdb") and preprocess_done_on_disk(sim):
        for name in ("protein_h.pdb", "protein.pdb"):
            cand = sim / "preprocess" / name
            if cand.is_file():
                state["cleaned_pdb"] = str(cand.resolve())
                break
    if not state.get("coordinates") and setup_done_on_disk(sim):
        for name in ("system.gro", "solvated.gro"):
            cand = sim / "simsetup" / name
            if cand.is_file():
                state["coordinates"] = str(cand.resolve())
                break
    done = list(state.get("completed_pipeline_stages") or [])
    for stage in PER_SIM_STAGES:
        if stage_done_on_disk(sim, stage) and stage not in done:
            done.append(stage)
    if done:
        state["completed_pipeline_stages"] = done
    return state


def mark_stage_done(state: Dict[str, Any], stage: str) -> None:
    key = normalize_stage(stage)
    done = list(state.get("completed_pipeline_stages") or [])
    if key not in done:
        done.append(key)
    state["completed_pipeline_stages"] = done


def stage_already_done(state: Dict[str, Any], stage: str) -> bool:
    key = normalize_stage(stage)
    if key in (state.get("completed_pipeline_stages") or []):
        return True
    sim = _sim_dir(state)
    if sim is not None and stage_done_on_disk(sim, key):
        return True
    if key == "preprocessing" and state.get("cleaned_pdb"):
        return Path(str(state["cleaned_pdb"])).is_file()
    if key == "simsetup" and state.get("coordinates"):
        return Path(str(state["coordinates"])).is_file()
    if key == "hpc" and (state.get("job_id") or state.get("reuse_hpc")):
        sim = _sim_dir(state)
        return bool(sim and hpc_done_on_disk(sim))
    if key == "analysis" and state.get("analysis_results"):
        return True
    return False


def advance_agent_index_past_done(
    state: Dict[str, Any],
    required_agents: Iterable[str],
) -> int:
    """Return the first required agent that is not already done.

    Never decrements. If every required agent is done, returns ``len(required)``.
    """
    restore_stage_artifacts(state)
    agents = [normalize_stage(a) for a in required_agents]
    idx = int(state.get("current_agent_idx") or 0)
    if idx < 0:
        idx = 0
    while idx < len(agents) and stage_already_done(state, agents[idx]):
        logger.info(
            "STAGE_TICK: %s already complete — advancing forward",
            agents[idx],
        )
        mark_stage_done(state, agents[idx])
        idx += 1
    return idx


def forbid_backward_route(state: Dict[str, Any], requested_node: str) -> Optional[str]:
    """If *requested_node* is behind completed work, return the next forward node."""
    restore_stage_artifacts(state)
    req = normalize_stage(requested_node)
    if req not in PER_SIM_STAGES:
        return None
    if not stage_already_done(state, req):
        return None
    # Find the next incomplete per-sim stage (campaign-level phases are separate).
    for stage in PER_SIM_STAGES:
        if not stage_already_done(state, stage):
            node = INTERNAL_TO_NODE.get(stage, stage)
            if node != requested_node:
                logger.info(
                    "STAGE_TICK: refusing rewind to %s; next forward node is %s",
                    requested_node,
                    node,
                )
            return node
    return "final_report"
