"""
Multi-simulation workflow progress — authoritative base-level routing state.

Stored in ``state["multi_sim_progress"]`` and persisted to
``{base}/supervisor/state.jsonl``.  Per-simulation detail lives in
``{sim}/supervisor/state.jsonl``; the base record says *which* sim and
*which* subtask to run next.

HITL ``switch {sim}`` only changes the chat view; ``continue`` always
follows ``multi_sim_progress``, not the HITL-bound simulation.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_CHECKPOINT_TO_AGENT = {
    "preprocess": "preprocessing",
    "preprocessing": "preprocessing",
    "setup": "simsetup",
    "hpc": "hpc",
    "analysis": "analysis",
    "reporter": "reporter",
}

_AGENT_TO_NODE = {
    "preprocessing": "preprocess",
    "simsetup": "setup",
    "hpc": "hpc",
    "analysis": "analysis",
    "reporter": "reporter",
}


def _required_agents(state: Dict[str, Any]) -> List[str]:
    from src.supervisor.unified_enricher import get_agent_execution_order

    subtask = state.get("subtask_type") or "full_task"
    return get_agent_execution_order(subtask, state)


def init_multi_sim_progress(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build or refresh progress from sim_prompts (call when master plan is ready)."""
    sim_prompts = state.get("sim_prompts") or []
    agents = _required_agents(state)
    if not sim_prompts:
        return state.get("multi_sim_progress") or {}

    sim_order: List[str] = []
    sims: Dict[str, Any] = {}
    for idx, sp in enumerate(sim_prompts):
        label = sp.get("label") or f"sim_{idx}"
        sim_order.append(label)
        sims[label] = {
            "index": idx,
            "working_dir": sp.get("working_dir") or "",
            "agents": {a: "pending" for a in agents},
            "status": "pending",
        }

    existing = state.get("multi_sim_progress") or {}
    # Preserve completed agents when re-init (e.g. replan)
    if existing.get("sim_order") == sim_order:
        for label, rec in existing.get("sims", {}).items():
            if label in sims and isinstance(rec, dict):
                sims[label]["agents"].update(rec.get("agents") or {})
                sims[label]["status"] = rec.get("status", sims[label]["status"])

    active_label = existing.get("active_sim_label") or sim_order[0]
    if active_label not in sims:
        active_label = sim_order[0]

    progress = {
        "version": 1,
        "sim_order": sim_order,
        "required_agents": agents,
        "phase": state.get("multi_sim_phase") or "executing_sims",
        "active_sim_label": active_label,
        "active_agent": existing.get("active_agent") or (agents[0] if agents else None),
        "sims": sims,
        "hitl_paused_at": existing.get("hitl_paused_at"),
    }
    if state.get("run_combined_analysis"):
        progress["combined"] = existing.get("combined") or {
            "analysis": "pending",
            "reporter": "pending",
        }
    state["multi_sim_progress"] = progress
    sync_state_from_progress(state)
    return progress


def reset_post_hpc_progress(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reset base-level progress for the sequential post-HPC analysis/reporter loop.

    Unlike ``init_multi_sim_progress``, this does not preserve stale agent status
    or active_sim_label from a prior interrupted run.
    """
    sim_prompts = state.get("sim_prompts") or []
    agents = ["analysis", "reporter"]
    sim_order: List[str] = []
    sims: Dict[str, Any] = {}
    for idx, sp in enumerate(sim_prompts):
        label = sp.get("label") or f"sim_{idx}"
        sim_order.append(label)
        sims[label] = {
            "index": idx,
            "working_dir": sp.get("working_dir") or "",
            "agents": {a: "pending" for a in agents},
            "status": "pending",
        }

    progress: Dict[str, Any] = {
        "version": 1,
        "sim_order": sim_order,
        "required_agents": agents,
        "phase": "executing_sims",
        "active_sim_label": sim_order[0] if sim_order else None,
        "active_agent": "analysis" if agents else None,
        "sims": sims,
        "hitl_paused_at": None,
    }
    if state.get("run_combined_analysis"):
        progress["combined"] = {"analysis": "pending", "reporter": "pending"}

    state["multi_sim_progress"] = progress
    state["current_sim_index"] = 0
    state["completed_sim_states"] = []
    state["current_agent_idx"] = 0
    state["plan_executed"] = False
    if sim_order:
        bind_workflow_to_sim(state, sim_order[0])
    return progress


def first_incomplete_post_hpc_sim(state: Dict[str, Any]) -> Optional[str]:
    """Return the label of the first sim with pending post-HPC agents."""
    progress = state.get("multi_sim_progress") or {}
    agents = progress.get("required_agents") or ["analysis", "reporter"]
    for label in progress.get("sim_order") or []:
        rec = _sim_record(progress, label)
        if not rec:
            continue
        agent_map = rec.get("agents") or {}
        if any(agent_map.get(a) != "done" for a in agents):
            return label
    return None


def all_per_sim_agents_done(state: Dict[str, Any]) -> bool:
    """True when every planned simulation finished all required agents."""
    progress = state.get("multi_sim_progress") or {}
    agents = progress.get("required_agents") or _required_agents(state)
    for label in progress.get("sim_order") or []:
        rec = _sim_record(progress, label)
        if not rec:
            return False
        agent_map = rec.get("agents") or {}
        if any(agent_map.get(a) != "done" for a in agents):
            return False
    return bool(progress.get("sim_order"))


def per_sim_post_hpc_artifacts_ready(working_dir: str) -> bool:
    """True when per-sim analysis summary and HTML report exist on disk."""
    wd = Path(working_dir)
    analysis_ok = (wd / "analysis" / "analysis_summary.jsonl").is_file()
    reporter_dir = wd / "reporter"
    reporter_ok = reporter_dir.is_dir() and any(reporter_dir.glob("*.html"))
    return analysis_ok and reporter_ok


def sync_post_hpc_progress_from_disk(state: Dict[str, Any]) -> None:
    """Align multi_sim_progress with on-disk post-HPC artifacts."""
    if not state.get("post_hpc_analysis_only"):
        return
    progress = ensure_multi_sim_progress(state)
    if not progress:
        return
    agents = progress.get("required_agents") or ["analysis", "reporter"]
    if set(agents) != {"analysis", "reporter"}:
        return
    for label in progress.get("sim_order") or []:
        rec = _sim_record(progress, label)
        if not rec:
            continue
        wd = rec.get("working_dir") or ""
        if not wd:
            base = state.get("multi_sim_base_dir") or state.get("working_directory")
            wd = str(Path(base) / label)
        agent_map = rec.setdefault("agents", {})
        analysis_ok = (Path(wd) / "analysis" / "analysis_summary.jsonl").is_file()
        reporter_ok = per_sim_post_hpc_artifacts_ready(wd)
        if analysis_ok:
            agent_map["analysis"] = "done"
        if reporter_ok:
            agent_map["reporter"] = "done"
        if all(agent_map.get(a) == "done" for a in agents):
            rec["status"] = "done"
    state["multi_sim_progress"] = progress


def all_post_hpc_artifacts_on_disk(state: Dict[str, Any]) -> bool:
    """True when every planned sim has analysis summary + reporter HTML on disk."""
    sim_prompts = state.get("sim_prompts") or []
    if not sim_prompts:
        return False
    for sp in sim_prompts:
        wd = sp.get("working_dir") or ""
        if not wd:
            base = state.get("multi_sim_base_dir") or state.get("working_directory")
            wd = str(Path(base) / (sp.get("label") or ""))
        if not per_sim_post_hpc_artifacts_ready(wd):
            return False
    return True


def ensure_multi_sim_progress(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if state.get("multi_sim_progress"):
        return state["multi_sim_progress"]
    if state.get("is_multi_simulation") and state.get("sim_prompts"):
        return init_multi_sim_progress(state)
    return None


def _sim_record(progress: Dict[str, Any], label: str) -> Optional[Dict[str, Any]]:
    return (progress.get("sims") or {}).get(label)


def mark_agent_status(
    state: Dict[str, Any],
    sim_label: str,
    agent_key: str,
    status: str,
) -> None:
    """Update agent status for a simulation (done | pending | in_progress | skipped)."""
    progress = ensure_multi_sim_progress(state)
    if not progress:
        return
    rec = _sim_record(progress, sim_label)
    if not rec:
        return
    agents = rec.setdefault("agents", {})
    internal = _CHECKPOINT_TO_AGENT.get(agent_key, agent_key)
    if internal == "simsetup":
        internal = "simsetup"
    # Normalize preprocessing name
    for key in list(agents.keys()):
        if key == internal or _CHECKPOINT_TO_AGENT.get(key, key) == internal:
            agents[key] = status
            break
    else:
        agents[internal] = status

    req = progress.get("required_agents") or []
    if req and all(agents.get(a) == "done" for a in req):
        rec["status"] = "done"
    elif any(agents.get(a) == "done" for a in req):
        rec["status"] = "in_progress"
    progress["active_sim_label"] = sim_label
    progress["active_agent"] = agent_key if status != "done" else progress.get("active_agent")
    state["multi_sim_progress"] = progress


def record_agent_finished(state: Dict[str, Any], agent_key: str) -> None:
    """Call when a field agent completes successfully (before HITL pause)."""
    phase = state.get("multi_sim_phase")
    if phase in ("combined_analysis", "combined_reporter"):
        progress = ensure_multi_sim_progress(state)
        if not progress:
            return
        progress["phase"] = phase
        combined = progress.setdefault("combined", {"analysis": "pending", "reporter": "pending"})
        combined[agent_key] = "done"
        progress["active_sim_label"] = None
        progress["active_agent"] = agent_key
        progress["hitl_paused_at"] = {
            "sim_label": None,
            "scope": "combined",
            "agent": agent_key,
            "checkpoint": f"human_{agent_key}_check",
        }
        state["multi_sim_progress"] = progress
        from agentic.hitl_router import bind_combined_hitl_view

        bind_combined_hitl_view(state, agent_key)
        return

    progress = ensure_multi_sim_progress(state)
    if not progress:
        return
    label = workflow_sim_label_for_hitl(state)
    if not label:
        return
    internal = agent_key
    if agent_key == "preprocess":
        internal = "preprocessing"
    mark_agent_status(state, label, internal, "done")
    progress = state["multi_sim_progress"]
    progress["hitl_paused_at"] = {
        "sim_label": label,
        "agent": internal,
        "checkpoint": f"human_{agent_key}_check" if agent_key != "preprocessing" else "human_preprocess_check",
    }
    state["multi_sim_progress"] = progress
    if label:
        state["hitl_target_sim_label"] = label


def workflow_sim_label_for_hitl(state: Dict[str, Any]) -> Optional[str]:
    """Simulation the workflow is executing (for HITL checkpoint display)."""
    progress = state.get("multi_sim_progress") or {}
    paused = progress.get("hitl_paused_at") or {}
    if paused.get("sim_label"):
        return paused["sim_label"]

    idx = state.get("current_sim_index")
    sim_prompts = state.get("sim_prompts") or []
    if idx is not None and 0 <= idx < len(sim_prompts):
        label = sim_prompts[idx].get("label")
        if label:
            return label

    wd = state.get("working_directory")
    base = state.get("multi_sim_base_dir") or state.get("working_directory")
    if wd and base:
        wdp = Path(wd).resolve()
        basep = Path(base).resolve()
        if wdp.parent == basep and wdp.name not in ("supervisor", "planner", "programmer"):
            return wdp.name

    if progress.get("active_sim_label"):
        return progress["active_sim_label"]
    return None


def _next_pending_agent(progress: Dict[str, Any], sim_label: str) -> Optional[str]:
    rec = _sim_record(progress, sim_label)
    if not rec:
        return None
    agents = progress.get("required_agents") or []
    done = rec.get("agents") or {}
    for a in agents:
        if done.get(a) != "done":
            return a
    return None


def _next_incomplete_sim(progress: Dict[str, Any]) -> Optional[str]:
    for label in progress.get("sim_order") or []:
        rec = _sim_record(progress, label)
        if rec and rec.get("status") != "done":
            return label
        if rec:
            agents = progress.get("required_agents") or []
            done = rec.get("agents") or {}
            if any(done.get(a) != "done" for a in agents):
                return label
    return None


def _reconcile_sim_agents_from_disk(rec: Dict[str, Any], agents: List[str]) -> None:
    """Update agent status from on-disk artifacts (resume / continue helper)."""
    if not rec:
        return
    sim_dir = Path(rec.get("working_dir") or "")
    if not sim_dir.is_dir():
        return
    rec.setdefault("agents", {})
    for agent in agents:
        sub = {
            "preprocessing": "preprocess",
            "simsetup": "simsetup",
            "hpc": "hpc",
            "analysis": "analysis",
            "reporter": "reporter",
        }.get(agent, agent)
        marker = sim_dir / sub
        if agent == "analysis" and (marker / "analysis_summary.jsonl").is_file():
            rec["agents"][agent] = "done"
        elif agent == "reporter" and list(marker.glob("*.html")):
            rec["agents"][agent] = "done"
        elif marker.is_dir() and any(marker.iterdir()):
            if rec["agents"].get(agent) != "done":
                rec["agents"][agent] = "in_progress"
    if all(rec["agents"].get(a) == "done" for a in agents):
        rec["status"] = "done"
    elif any(rec["agents"].get(a) == "done" for a in agents):
        rec["status"] = "in_progress"


def reconcile_progress_from_disk(state: Dict[str, Any], progress: Dict[str, Any]) -> None:
    """Refresh per-sim agent completion from artifacts before HITL continue/resume."""
    agents = progress.get("required_agents") or _required_agents(state)
    for label in progress.get("sim_order") or []:
        rec = _sim_record(progress, label)
        if rec:
            _reconcile_sim_agents_from_disk(rec, agents)


def _combined_analysis_done_on_disk(base: Path) -> bool:
    """True when base-level combined analysis artifacts exist."""
    analysis_dir = base / "analysis"
    if not analysis_dir.is_dir():
        return False
    markers = (
        analysis_dir / "classification_features.csv",
        analysis_dir / "classification_clusters.json",
        analysis_dir / "com_distance_overlay.png",
        analysis_dir / "ligand_rmsf_overlay.png",
        analysis_dir / "pocket_rmsf_overlay.png",
    )
    if any(path.is_file() for path in markers):
        return True
    return any(analysis_dir.glob("*_overlay.png"))


def _combined_reporter_done_on_disk(base: Path) -> bool:
    """True when the base-level combined HTML report exists."""
    reporter_dir = base / "reporter"
    return (reporter_dir / "combined_report.html").is_file()


def reconcile_multisim_progress_from_disk(
    state: Dict[str, Any],
    base_dir: Optional[str] = None,
) -> None:
    """
    Refresh multi_sim_progress from on-disk artifacts before resume routing.

    Ensures ``--resume`` skips per-simulation work (and combined analysis) that
    already finished, even when the saved checkpoint still shows ``pending``.
    """
    if not state.get("is_multi_simulation"):
        return
    if not state.get("sim_prompts") and not state.get("multi_sim_progress"):
        return

    base = Path(
        base_dir
        or state.get("multi_sim_base_dir")
        or state.get("working_directory")
        or "."
    ).resolve()

    if not state.get("multi_sim_progress"):
        init_multi_sim_progress(state)

    progress = state.get("multi_sim_progress") or {}
    agents = progress.get("required_agents") or _required_agents(state)
    for label in progress.get("sim_order") or []:
        rec = _sim_record(progress, label)
        if not rec:
            continue
        wd = rec.get("working_dir") or str(base / label)
        rec["working_dir"] = wd
        _reconcile_sim_agents_from_disk(rec, agents)

    wants_combined = bool(
        state.get("run_combined_analysis")
        or progress.get("combined")
        or _combined_analysis_done_on_disk(base)
        or _combined_reporter_done_on_disk(base)
    )
    if wants_combined:
        combined = progress.setdefault(
            "combined",
            {"analysis": "pending", "reporter": "pending"},
        )
        if _combined_analysis_done_on_disk(base):
            combined["analysis"] = "done"
        if _combined_reporter_done_on_disk(base):
            combined["reporter"] = "done"
        state["run_combined_analysis"] = True

    if all_per_sim_agents_done(state):
        combined = progress.get("combined") or {}
        if combined:
            if combined.get("analysis") != "done":
                progress["phase"] = "combined_analysis"
                progress["active_sim_label"] = None
                progress["active_agent"] = "analysis"
            elif combined.get("reporter") != "done":
                progress["phase"] = "combined_reporter"
                progress["active_sim_label"] = None
                progress["active_agent"] = "reporter"
            else:
                progress["phase"] = "complete"
                progress["active_sim_label"] = None
                progress["active_agent"] = None
        else:
            progress["phase"] = "complete"
            progress["active_sim_label"] = None
            progress["active_agent"] = None
    else:
        progress["phase"] = "executing_sims"
        active = _next_incomplete_sim(progress)
        if active:
            progress["active_sim_label"] = active
            progress["active_agent"] = _next_pending_agent(progress, active)

    state["multi_sim_progress"] = progress
    sync_state_from_progress(state)
    logger.info(
        "[resume] Reconciled multi_sim_progress from disk at %s\n%s",
        base,
        progress_summary(state),
    )


def _workflow_pause_sim(progress: Dict[str, Any], state: Dict[str, Any]) -> Optional[str]:
    """
    Simulation where the workflow paused for HITL (authoritative for continue).

    Ignores HITL chat ``switch`` binds — only ``hitl_paused_at`` and progress.
    """
    paused = progress.get("hitl_paused_at") or {}
    if paused.get("sim_label"):
        return paused["sim_label"]
    label = _next_incomplete_sim(progress)
    if label:
        return label
    return progress.get("active_sim_label")


def _sim_all_agents_done(progress: Dict[str, Any], sim_label: str) -> bool:
    rec = _sim_record(progress, sim_label)
    if not rec:
        return False
    agents = progress.get("required_agents") or []
    done = rec.get("agents") or {}
    if not agents:
        return rec.get("status") == "done"
    return all(done.get(a) == "done" for a in agents)


def _route_after_per_sim_continue(
    progress: Dict[str, Any],
    pause_sim: str,
    finished_agent: str,
    agent_was_done_before_continue: bool,
) -> Optional[tuple]:
    """
    Return (target_sim, target_agent) after *finished_agent* was marked done on *pause_sim*.

    When the pause sim is already fully complete (e.g. reporter exists on disk but
    progress was stale), advance to the next incomplete simulation.
    """
    rec = _sim_record(progress, pause_sim)
    if not rec:
        return None

    if _sim_all_agents_done(progress, pause_sim):
        rec["status"] = "done"
        nxt = _next_incomplete_sim(progress)
        if nxt:
            return nxt, _next_pending_agent(progress, nxt)
        return None

    if agent_was_done_before_continue:
        pending = _next_pending_agent(progress, pause_sim)
        if pending:
            return pause_sim, pending
        nxt = _next_incomplete_sim(progress)
        if nxt:
            return nxt, _next_pending_agent(progress, nxt)
        return None

    pending = _next_pending_agent(progress, pause_sim)
    if pending:
        return pause_sim, pending

    nxt = _next_incomplete_sim(progress)
    if nxt:
        return nxt, _next_pending_agent(progress, nxt)
    return None


def resolve_active_sim_label(state: Dict[str, Any]) -> Optional[str]:
    """Best-effort label for the simulation currently being prepared or executed."""
    sim_case = state.get("sim_case") or {}
    if sim_case.get("label") and (
        state.get("hpc_pool_prep_only")
        or state.get("post_hpc_analysis_only")
        or state.get("multi_sim_phase") == "executing_sims"
    ):
        return sim_case["label"]

    if state.get("hpc_pool_prep_only"):
        from agentic.multi_sim_hpc_pool import _next_prep_label

        pool = state.get("hpc_pool") or {}
        pending = _next_prep_label(pool, state.get("sim_prompts") or [])
        if pending:
            return pending

    progress = state.get("multi_sim_progress") or {}
    if progress.get("active_sim_label"):
        return progress["active_sim_label"]

    sim_prompts = state.get("sim_prompts") or []
    idx = state.get("current_sim_index", 0)
    if sim_prompts and 0 <= idx < len(sim_prompts):
        return sim_prompts[idx].get("label")
    return None


def ensure_per_sim_working_directory(state: Dict[str, Any]) -> bool:
    """
    Align ``working_directory`` with the active per-sim context.

    Prevents stale ``multi_sim_progress.active_sim_label`` from routing prep
    for sim N+1 into sim N's directory after checkpoint restore or sync.
    """
    if not state.get("is_multi_simulation") or state.get("combined_only"):
        return False

    phase = state.get("multi_sim_phase")
    if phase == "hpc_pool":
        if not state.get("hpc_pool_prep_only") and not state.get("post_hpc_analysis_only"):
            return False
    elif phase != "executing_sims":
        return False

    label = resolve_active_sim_label(state)
    if not label:
        return False

    sim_prompts = state.get("sim_prompts") or []
    idx = next(
        (i for i, sp in enumerate(sim_prompts) if sp.get("label") == label),
        None,
    )
    if idx is None:
        return False

    sp = sim_prompts[idx]
    base = state.get("multi_sim_base_dir") or state.get("working_directory") or "."
    expected_wd = sp.get("working_dir") or str(Path(base) / label)
    expected_wd = str(Path(expected_wd).resolve())
    current_wd = str(Path(state.get("working_directory", ".")).resolve())

    if current_wd == expected_wd:
        state["current_sim_index"] = idx
        return False

    bind_workflow_to_sim(state, label)
    state["current_sim_index"] = idx
    progress = state.get("multi_sim_progress") or {}
    if progress:
        progress["active_sim_label"] = label
        state["multi_sim_progress"] = progress

    from agentic.utils.conversation_logger import set_log_file

    set_log_file(str(Path(expected_wd) / "agent_conversation.log"))
    logger.warning(
        "Re-bound working_directory to %s for active sim %s (was %s)",
        expected_wd,
        label,
        current_wd,
    )
    return True


def bind_workflow_to_sim(state: Dict[str, Any], sim_label: str) -> None:
    """Point workflow routing fields at *sim_label* without wiping artifacts."""
    progress = ensure_multi_sim_progress(state)
    if not progress:
        return
    rec = _sim_record(progress, sim_label)
    if not rec:
        return
    wd = rec.get("working_dir") or ""
    if not wd:
        base = state.get("multi_sim_base_dir") or state.get("working_directory")
        wd = str(Path(base) / sim_label)
    wd = str(Path(wd).resolve())
    state["working_directory"] = wd
    state["current_sim_index"] = rec.get("index", 0)
    state["preprocess_dir"] = str(Path(wd) / "preprocess")
    state["simsetup_dir"] = str(Path(wd) / "simsetup")
    state["hpc_dir"] = str(Path(wd) / "hpc")
    state["analysis_dir"] = str(Path(wd) / "analysis")
    state["analysis_directory"] = str(Path(wd) / "analysis")
    state["reporter_dir"] = str(Path(wd) / "reporter")
    progress["active_sim_label"] = sim_label
    state["multi_sim_progress"] = progress


def sync_state_from_progress(state: Dict[str, Any]) -> None:
    """Apply multi_sim_progress → current_sim_index, current_agent_idx, plan_executed."""
    progress = state.get("multi_sim_progress")
    if not progress:
        return
    label = progress.get("active_sim_label")
    agent = progress.get("active_agent")
    if label:
        bind_workflow_to_sim(state, label)
    agents = progress.get("required_agents") or _required_agents(state)
    if agent and agent in agents:
        state["current_agent_idx"] = agents.index(agent)
    rec = _sim_record(progress, label) if label else None
    if rec and rec.get("status") == "done":
        state["plan_executed"] = True
    else:
        state["plan_executed"] = False
    phase = progress.get("phase")
    if phase and state.get("multi_sim_phase") != "hpc_pool":
        state["multi_sim_phase"] = phase
    elif state.get("multi_sim_phase") == "hpc_pool":
        progress["phase"] = "hpc_pool"
        state["multi_sim_progress"] = progress
    ensure_per_sim_working_directory(state)


def apply_hitl_continue(state: Dict[str, Any], checkpoint_type: str) -> None:
    """
    Deterministic routing after HITL ``continue`` / ``approved``.

    Uses base-level ``multi_sim_progress`` — ignores HITL chat sim binding.
    """
    phase = state.get("multi_sim_phase")
    if phase == "combined_analysis" and checkpoint_type == "analysis":
        progress = ensure_multi_sim_progress(state) or {}
        combined = progress.setdefault("combined", {})
        combined["analysis"] = "done"
        combined["reporter"] = "in_progress"
        progress["phase"] = "combined_reporter"
        progress["active_sim_label"] = None
        progress["active_agent"] = "reporter"
        progress["hitl_paused_at"] = None
        state["multi_sim_progress"] = progress
        state["multi_sim_phase"] = "combined_reporter"
        state["current_agent_idx"] = 1
        state["plan_executed"] = False
        state["next_node"] = "reporter"
        from agentic.hitl_router import bind_combined_hitl_view

        bind_combined_hitl_view(state, "reporter")
        logger.info("HITL continue: combined analysis done → combined reporter")
        return

    if phase == "combined_reporter" and checkpoint_type == "reporter":
        progress = ensure_multi_sim_progress(state) or {}
        combined = progress.setdefault("combined", {})
        combined["reporter"] = "done"
        progress["phase"] = "complete"
        progress["hitl_paused_at"] = None
        state["multi_sim_progress"] = progress
        state["multi_sim_phase"] = "complete"
        state["plan_executed"] = True
        state["next_node"] = "final_report"
        logger.info("HITL continue: combined reporter done → final report")
        return

    progress = ensure_multi_sim_progress(state)
    if not progress:
        from agentic.hitl_router import restore_multi_sim_executing_working_directory

        restore_multi_sim_executing_working_directory(state)
        state["next_node"] = "supervisor"
        state["plan_executed"] = False
        return

    reconcile_progress_from_disk(state, progress)
    state["multi_sim_progress"] = progress

    paused = progress.get("hitl_paused_at") or {}
    finished_agent = _CHECKPOINT_TO_AGENT.get(checkpoint_type, checkpoint_type)
    pause_sim = _workflow_pause_sim(progress, state)
    if not pause_sim:
        pause_sim = (progress.get("sim_order") or [None])[0]
    if not pause_sim:
        state["next_node"] = "supervisor"
        return

    rec = _sim_record(progress, pause_sim)
    agent_already_done = bool(
        rec and (rec.get("agents") or {}).get(finished_agent) == "done"
    )
    if not agent_already_done:
        mark_agent_status(state, pause_sim, finished_agent, "done")
        progress = state["multi_sim_progress"]

    progress["hitl_paused_at"] = None
    route = _route_after_per_sim_continue(
        progress, pause_sim, finished_agent, agent_already_done
    )

    if route:
        target_sim, next_agent = route
        if target_sim != pause_sim:
            rec = _sim_record(progress, pause_sim)
            if rec:
                rec["status"] = "done"
        progress["active_sim_label"] = target_sim
        progress["active_agent"] = next_agent
        state["multi_sim_progress"] = progress
        bind_workflow_to_sim(state, target_sim)
        if next_agent:
            mark_agent_status(state, target_sim, next_agent, "in_progress")
            progress = state["multi_sim_progress"]
            state["current_agent_idx"] = (progress.get("required_agents") or []).index(next_agent)
        state["plan_executed"] = False

        if target_sim != pause_sim:
            state["next_node"] = "supervisor"
            state["_hitl_start_next_sim"] = True
            logger.info(
                "HITL continue: %s complete (paused at %s/%s) → advance to sim %s agent %s",
                pause_sim, pause_sim, finished_agent, target_sim, next_agent,
            )
            return

        state["next_node"] = _AGENT_TO_NODE.get(next_agent, next_agent)
        logger.info(
            "HITL continue: %s/%s done → next %s on %s",
            pause_sim, finished_agent, next_agent, target_sim,
        )
        return

    # All per-sim work done — start combined analysis/report if requested
    if state.get("run_combined_analysis") is True:
        progress["phase"] = "combined_analysis"
        progress["active_sim_label"] = None
        progress["active_agent"] = "analysis"
        combined = progress.setdefault("combined", {"analysis": "pending", "reporter": "pending"})
        combined["analysis"] = "in_progress"
        state["multi_sim_progress"] = progress
        state["plan_executed"] = False
        state["_hitl_start_combined"] = True
        state["next_node"] = "supervisor"
        logger.info("HITL continue: all per-simulation subtasks complete → combined analysis")
        return

    progress["phase"] = "executing_sims"
    state["multi_sim_progress"] = progress
    state["plan_executed"] = True
    state["next_node"] = "supervisor"
    logger.info("HITL continue: all per-simulation subtasks complete")


def progress_summary(state: Dict[str, Any]) -> str:
    progress = state.get("multi_sim_progress")
    if not progress:
        return ""
    lines = ["Multi-sim progress:"]
    for label in progress.get("sim_order") or []:
        rec = _sim_record(progress, label) or {}
        agents = rec.get("agents") or {}
        parts = ", ".join(f"{a}={agents.get(a, '?')}" for a in (progress.get("required_agents") or []))
        mark = " ← active" if label == progress.get("active_sim_label") else ""
        lines.append(f"  {label}: [{parts}] status={rec.get('status', '?')}{mark}")
    nxt = progress.get("active_agent")
    active = progress.get("active_sim_label")
    if active:
        lines.append(f"  Next step: {nxt} on {active}")
    combined = progress.get("combined") or {}
    if combined:
        lines.append(
            f"  Combined: analysis={combined.get('analysis', '?')}, "
            f"reporter={combined.get('reporter', '?')}"
        )
    return "\n".join(lines)


def rebuild_progress_from_disk(state: Dict[str, Any], base_dir: str) -> None:
    """Infer progress from per-sim supervisor state + artifacts (resume helper)."""
    reconcile_multisim_progress_from_disk(state, base_dir)


def multisim_workflow_incomplete(progress: Optional[Dict[str, Any]]) -> bool:
    """True when base-level progress shows per-sim or combined work still pending."""
    if not progress:
        return False
    for label in progress.get("sim_order") or []:
        rec = _sim_record(progress, label)
        if rec and rec.get("status") != "done":
            return True
        if rec:
            agents = progress.get("required_agents") or []
            done = rec.get("agents") or {}
            if any(done.get(a) != "done" for a in agents):
                return True
    combined = progress.get("combined")
    if combined:
        if combined.get("analysis") != "done" or combined.get("reporter") != "done":
            return True
    return False


def prepare_multisim_resume_state(state: Dict[str, Any]) -> Optional[str]:
    """
    Point workflow at the next incomplete sim/agent from ``multi_sim_progress``.

    Returns the simulation label resumed, or None if nothing to resume.
    """
    progress = state.get("multi_sim_progress")
    if not multisim_workflow_incomplete(progress):
        return None
    label = _next_incomplete_sim(progress or {})
    if not label:
        combined = (progress or {}).get("combined") or {}
        if combined.get("analysis") != "done":
            progress["phase"] = "combined_analysis"
            progress["active_sim_label"] = None
            progress["active_agent"] = "analysis"
            state["multi_sim_progress"] = progress
            state["multi_sim_phase"] = "combined_analysis"
            state["plan_executed"] = False
            state["execution_plan"] = None
            state["_hitl_start_combined"] = True
            state["next_node"] = "supervisor"
            logger.info("[resume] Multi-sim per-sim done — resuming combined analysis")
            return "__combined__"
        if combined.get("reporter") != "done":
            progress["phase"] = "combined_reporter"
            progress["active_sim_label"] = None
            progress["active_agent"] = "reporter"
            state["multi_sim_progress"] = progress
            state["multi_sim_phase"] = "combined_reporter"
            state["plan_executed"] = False
            state["execution_plan"] = None
            state["current_agent_idx"] = 1
            from agentic.hitl_router import bind_combined_hitl_view

            bind_combined_hitl_view(state, "reporter")
            state["next_node"] = "reporter"
            logger.info("[resume] Multi-sim combined analysis done — resuming combined reporter")
            return "__combined_reporter__"
        return None
    rec = _sim_record(progress, label)
    if not rec:
        return None
    next_agent = _next_pending_agent(progress, label)
    progress["active_sim_label"] = label
    progress["active_agent"] = next_agent
    state["multi_sim_progress"] = progress
    state["current_sim_index"] = rec.get("index", 0)
    state["multi_sim_phase"] = "executing_sims"
    state["plan_executed"] = False
    state["execution_plan"] = None
    sync_state_from_progress(state)
    logger.info(
        "[resume] Multi-sim progress → sim %s agent %s (index %s)",
        label,
        next_agent,
        state.get("current_sim_index"),
    )
    return label

