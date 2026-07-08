"""
Cross-simulation HPC job pool for multi-sim workflows.

When preprocess/simsetup + HPC + analysis/reporter are requested together,
simulations are prepared sequentially and SLURM jobs are submitted up to
*max_concurrent* at a time. The supervisor polls SLURM (default every 120 min)
until all jobs finish, then runs per-sim analysis/reporter and combined work.

Hybrid execution: blocks with sleep while the process is alive; ``--resume``
restores pool state from ``{base}/supervisor/state.jsonl``.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

_TERMINAL_SUCCESS = frozenset({"COMPLETED", "COMPLETING"})
_TERMINAL_FAILURE = frozenset({"FAILED", "CANCELLED", "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY"})
_PRODUCTION_TRAJECTORIES = ("mdWrap.xtc", "md.xtc", "prod.xtc", "production.xtc")


def _md_production_finished(hpc_dir: Path) -> bool:
    """True when production ``md.log`` reports mdrun finished (not equil logs)."""
    md_log = hpc_dir / "md.log"
    if not md_log.is_file():
        return False
    try:
        text = md_log.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return "Finished mdrun" in text


def _sim_production_trajectory_ready(sim_dir: str) -> bool:
    """Production trajectory complete — equilibration ``nvt``/``npt`` files do not count."""
    hpc = Path(sim_dir) / "hpc"
    if not hpc.is_dir():
        return False
    has_prod = any((hpc / name).is_file() and (hpc / name).stat().st_size > 0 for name in _PRODUCTION_TRAJECTORIES)
    if not has_prod:
        return False
    return _md_production_finished(hpc)


def _sim_trajectory_ready(sim_dir: str) -> bool:
    """Backward-compatible alias used by supervisor helpers."""
    return _sim_production_trajectory_ready(sim_dir)


def _log_hpc_pool_event(
    sim_working_dir: str,
    label: str,
    event: str,
    rec: Dict[str, Any],
) -> None:
    """Write HPC pool SLURM sync events to the per-simulation conversation log."""
    from agentic.utils.conversation_logger import (
        log_agent_action,
        log_agent_completion,
        set_log_file,
    )

    log_path = str(Path(sim_working_dir) / "agent_conversation.log")
    Path(sim_working_dir).mkdir(parents=True, exist_ok=True)
    set_log_file(log_path)
    if event == "completed":
        log_agent_completion(
            "hpc",
            "HPC Job Submission (pool mode)",
            {
                "mode": "hpc_pool",
                "simulation": label,
                "job_id": rec.get("job_id"),
                "job_status": rec.get("last_slurm_state") or "COMPLETED",
                "trajectory_ready": rec.get("trajectory_ready"),
            },
            True,
        )
    else:
        log_agent_action(
            "hpc",
            f"HPC pool: {event}",
            {
                "simulation": label,
                "job_id": rec.get("job_id"),
                "slurm_state": rec.get("last_slurm_state"),
                "hpc_status": rec.get("hpc_status"),
            },
        )


def _base_conversation_log(state: Dict[str, Any]) -> Optional[str]:
    base = state.get("multi_sim_base_dir") or state.get("working_directory")
    if not base:
        return None
    return str(Path(base) / "agent_conversation.log")


def _label_for_job_id(pool: Dict[str, Any], job_id: str) -> Optional[str]:
    for label, rec in (pool.get("sims") or {}).items():
        if str(rec.get("job_id") or "") == job_id:
            return label
    return None


def _slurm_snapshot_for_pool(pool: Dict[str, Any], by_id: Dict[str, Any]) -> Dict[str, Any]:
    pool_ids = {
        str(rec.get("job_id"))
        for rec in (pool.get("sims") or {}).values()
        if rec.get("job_id")
    }
    pool_jobs: List[Dict[str, Any]] = []
    for jid in sorted(pool_ids):
        job = by_id.get(jid) or {}
        pool_jobs.append(
            {
                "sim": _label_for_job_id(pool, jid),
                "job_id": jid,
                "state": job.get("state", "NOT_IN_QUEUE"),
                "partition": job.get("partition"),
                "time_left": job.get("time_left"),
                "name": job.get("name"),
            }
        )
    return {
        "pool_jobs_in_queue": pool_jobs,
        "jobs_in_sq_total": len(by_id),
    }


def log_pool_to_base(
    state: Dict[str, Any],
    action: str,
    *,
    pool: Optional[Dict[str, Any]] = None,
    by_id: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Log cross-sim pool management to ``{base}/agent_conversation.log``."""
    log_path = _base_conversation_log(state)
    if not log_path:
        return
    from agentic.utils.conversation_logger import log_agent_action, set_log_file

    pool = pool or state.get("hpc_pool") or {}
    details: Dict[str, Any] = {
        "active_slots": f"{_count_running(pool)}/{pool.get('max_concurrent', '?')}",
        "pool_status": pool_summary(state),
    }
    if by_id is not None:
        details["slurm_queue"] = _slurm_snapshot_for_pool(pool, by_id)
    if extra:
        details.update(extra)
    set_log_file(log_path)
    log_agent_action("hpc_pool", action, details)


def parse_hpc_check_interval(value: Any, default_sec: int = 7200) -> int:
    """Parse ``2h``, ``120m``, ``7200``, or seconds int."""
    if value is None:
        return default_sec
    if isinstance(value, (int, float)):
        return max(60, int(value))
    text = str(value).strip().lower()
    if not text:
        return default_sec
    if text.isdigit():
        return max(60, int(text))
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([smhd])$", text)
    if not m:
        return default_sec
    num = float(m.group(1))
    unit = m.group(2)
    mult = {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]
    return max(60, int(num * mult))


def should_use_hpc_pool(state: Dict[str, Any]) -> bool:
    """True when multi-sim runs pre-HPC and post-HPC agents in one workflow."""
    if not state.get("is_multi_simulation"):
        return False
    if state.get("combined_only") or state.get("hpc_pool_disabled"):
        return False
    from src.supervisor.unified_enricher import get_agent_execution_order

    agents = get_agent_execution_order(state.get("subtask_type") or "full_task", state)
    pre = any(a in agents for a in ("preprocessing", "simsetup"))
    post = any(a in agents for a in ("analysis", "reporter"))
    return pre and "hpc" in agents and post


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _sim_setup_ready(sim_dir: str) -> bool:
    simsetup = Path(sim_dir) / "simsetup"
    if not simsetup.is_dir():
        return False
    return any(simsetup.glob("*.gro")) or any(simsetup.glob("*.top"))


def _revalidate_pool_sim(rec: Dict[str, Any]) -> None:
    """Fix spurious skip/complete flags when only equilibration trajectories exist."""
    wd = rec.get("working_dir") or ""
    prod_ready = _sim_production_trajectory_ready(wd)
    hpc = rec.get("hpc_status")

    if prod_ready:
        rec["prep_status"] = "skipped"
        rec["hpc_status"] = "skipped"
        rec["skip_reason"] = "production trajectory on disk"
        rec.pop("job_id", None)
        rec.pop("job_script", None)
        rec.pop("last_slurm_state", None)
        return

    if hpc in ("skipped", "completed"):
        jid = rec.get("job_id")
        last = str(rec.get("last_slurm_state") or "").upper()
        if jid and last in ("RUNNING", "COMPLETING", "R"):
            rec["hpc_status"] = "running"
        elif jid and last in ("PENDING", "PD"):
            rec["hpc_status"] = "submitted"
        elif jid:
            rec["hpc_status"] = "submitted"
        elif _sim_setup_ready(wd):
            rec["prep_status"] = "done"
            rec["hpc_status"] = "pending"
        else:
            rec["prep_status"] = "pending"
            rec["hpc_status"] = "pending"
        rec.pop("skip_reason", None)
        if rec.get("hpc_status") == "pending":
            rec.pop("job_id", None)
            rec.pop("job_script", None)
            rec.pop("last_slurm_state", None)


def init_hpc_pool(state: Dict[str, Any]) -> Dict[str, Any]:
    """Build or refresh ``state['hpc_pool']`` from ``sim_prompts``."""
    from agentic.parallel_resources import resolve_allowed_hpc_jobs

    sim_prompts = state.get("sim_prompts") or []
    max_concurrent = resolve_allowed_hpc_jobs(state)
    interval = parse_hpc_check_interval(
        state.get("hpc_check_interval"),
        default_sec=int(state.get("hpc_check_interval_sec") or 7200),
    )
    existing = state.get("hpc_pool") or {}
    sims: Dict[str, Any] = dict(existing.get("sims") or {})

    for idx, sp in enumerate(sim_prompts):
        label = sp.get("label") or f"sim_{idx}"
        wd = sp.get("working_dir") or ""
        rec = sims.get(label) or {}
        rec.setdefault("label", label)
        rec.setdefault("index", idx)
        rec["working_dir"] = wd
        if _sim_production_trajectory_ready(wd):
            rec["prep_status"] = "skipped"
            rec["hpc_status"] = "skipped"
            rec["skip_reason"] = "production trajectory on disk"
            rec.pop("job_id", None)
            rec.pop("job_script", None)
            rec.pop("last_slurm_state", None)
        elif _sim_setup_ready(wd):
            rec["prep_status"] = "done"
            if rec.get("hpc_status") not in ("submitted", "running", "completed", "skipped"):
                rec["hpc_status"] = "pending"
        else:
            if rec.get("prep_status") == "done":
                logger.warning(
                    "HPC pool: %s marked prep done but simsetup not ready — resetting to pending",
                    label,
                )
            rec["prep_status"] = "pending"
            if rec.get("hpc_status") == "failed" and not rec.get("job_id"):
                rec["hpc_status"] = "pending"
                rec.pop("error", None)
            elif rec.get("hpc_status") not in ("submitted", "running", "completed", "skipped"):
                rec["hpc_status"] = "pending"
        _revalidate_pool_sim(rec)
        sims[label] = rec

    prep_cursor = existing.get("prep_cursor", 0)
    pool = {
        "version": 1,
        "max_concurrent": max_concurrent,
        "check_interval_sec": interval,
        "last_check_at": existing.get("last_check_at"),
        "awaiting_hitl": existing.get("awaiting_hitl", False),
        "hitl_reason": existing.get("hitl_reason"),
        "sims": sims,
        "prep_cursor": prep_cursor,
        "phase": existing.get("phase") or "active",
    }
    state["hpc_pool"] = pool
    state["allowed_hpc_jobs"] = max_concurrent
    state["hpc_check_interval_sec"] = interval
    return pool


def _count_running(pool: Dict[str, Any]) -> int:
    n = 0
    for rec in (pool.get("sims") or {}).values():
        if rec.get("hpc_status") in ("submitted", "running"):
            n += 1
    return n


def _all_hpc_done(pool: Dict[str, Any]) -> bool:
    if _count_running(pool) > 0:
        return False
    sims = pool.get("sims") or {}
    if not sims:
        return False
    for rec in sims.values():
        st = rec.get("hpc_status")
        wd = rec.get("working_dir") or ""
        if st == "skipped":
            if not _sim_production_trajectory_ready(wd):
                return False
        elif st != "completed":
            return False
        elif not _sim_production_trajectory_ready(wd):
            return False
    return True


def _sync_jobs_from_slurm(state: Dict[str, Any], pool: Dict[str, Any], *, force: bool = False) -> None:
    """Update pool sim records from ``list_my_slurm_jobs`` / ``check_job_status``."""
    from src.hpc.job_monitor import list_my_slurm_jobs, check_job_status

    now = _utc_now()
    last = pool.get("last_check_at")
    interval = int(pool.get("check_interval_sec") or 7200)
    if not force and last:
        try:
            prev = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if (now - prev).total_seconds() < interval:
                return
        except ValueError:
            pass

    queue = list_my_slurm_jobs.func()
    by_id = {}
    if queue.get("success"):
        for job in queue.get("jobs") or []:
            by_id[str(job.get("job_id"))] = job

    for label, rec in (pool.get("sims") or {}).items():
        st = rec.get("hpc_status")
        if st not in ("submitted", "running"):
            continue
        jid = str(rec.get("job_id") or "")
        if not jid:
            continue
        prev_status = st
        wd = rec.get("working_dir") or ""
        if jid in by_id:
            slurm_state = str(by_id[jid].get("state", "RUNNING")).upper()
            rec["last_slurm_state"] = slurm_state
            if slurm_state in ("RUNNING", "COMPLETING"):
                rec["hpc_status"] = "running"
            elif slurm_state == "PENDING":
                rec["hpc_status"] = "submitted"
            continue

        status = check_job_status.func(job_id=jid)
        if not status.get("success"):
            continue
        slurm_state = str(status.get("status", "UNKNOWN")).upper()
        rec["last_slurm_state"] = slurm_state
        if slurm_state in _TERMINAL_SUCCESS or slurm_state == "COMPLETED":
            if _sim_production_trajectory_ready(wd):
                rec["hpc_status"] = "completed"
                rec["trajectory_ready"] = True
                if prev_status != "completed":
                    _log_hpc_pool_event(wd, label, "completed", rec)
            else:
                rec["hpc_status"] = "running"
                logger.info(
                    "HPC pool: %s job %s left SLURM queue but production trajectory not ready yet",
                    label,
                    jid,
                )
        elif slurm_state in _TERMINAL_FAILURE:
            rec["hpc_status"] = "failed"
            rec["error"] = f"SLURM job {jid} ended with {slurm_state}"
            _log_hpc_pool_event(wd, label, f"failed ({slurm_state})", rec)
        elif slurm_state in ("RUNNING", "R"):
            rec["hpc_status"] = "running"
        elif slurm_state in ("PENDING", "PD"):
            rec["hpc_status"] = "submitted"

    pool["last_check_at"] = now.isoformat()
    state["hpc_pool"] = pool
    log_pool_to_base(state, "SLURM poll sync (sq --me)", pool=pool, by_id=by_id)


def _submit_ready_sims(state: Dict[str, Any], pool: Dict[str, Any]) -> List[str]:
    """Submit jobs for prepared sims while slots remain. Returns labels submitted."""
    from agentic.hpc.pool_submit import submit_simulation_job
    from src.hpc.job_monitor import list_my_slurm_jobs

    submitted: List[str] = []
    slots = int(pool.get("max_concurrent") or 5) - _count_running(pool)
    if slots <= 0:
        return submitted

    order = [sp.get("label") for sp in (state.get("sim_prompts") or [])]
    for label in order:
        if slots <= 0:
            break
        rec = (pool.get("sims") or {}).get(label)
        if not rec:
            continue
        if rec.get("prep_status") not in ("done", "skipped"):
            continue
        if rec.get("hpc_status") != "pending":
            continue
        wd = rec.get("working_dir") or ""
        if _sim_production_trajectory_ready(wd):
            rec["hpc_status"] = "skipped"
            rec["skip_reason"] = "production trajectory on disk"
            rec.pop("job_id", None)
            continue
        result = submit_simulation_job(wd, label, workflow_state=state)
        if result.get("success"):
            rec["hpc_status"] = "submitted"
            rec["job_id"] = result.get("job_id")
            rec["job_script"] = result.get("job_script")
            rec["job_name"] = result.get("job_name")
            rec.pop("error", None)
            submitted.append(label)
            slots -= 1
            logger.info("HPC pool: submitted %s job_id=%s", label, rec.get("job_id"))
        else:
            err = result.get("error", "submit failed")
            if not _sim_setup_ready(wd):
                rec["prep_status"] = "pending"
                rec["hpc_status"] = "pending"
                rec.pop("error", None)
                logger.warning(
                    "HPC pool: %s submit skipped — prep incomplete (%s)",
                    label,
                    err,
                )
                continue
            rec["hpc_status"] = "failed"
            rec["error"] = err
            pool["awaiting_hitl"] = True
            pool["hitl_reason"] = f"Submit failed for {label}: {rec['error']}"
            logger.error("HPC pool: submit failed for %s: %s", label, rec["error"])
            break

    if submitted:
        queue = list_my_slurm_jobs.func()
        by_id = {}
        if queue.get("success"):
            for job in queue.get("jobs") or []:
                by_id[str(job.get("job_id"))] = job
        log_pool_to_base(
            state,
            f"Submitted pool jobs: {', '.join(submitted)}",
            pool=pool,
            by_id=by_id,
            extra={"submitted_labels": submitted},
        )

    state["hpc_pool"] = pool
    return submitted


def _next_prep_label(pool: Dict[str, Any], sim_prompts: List[Dict]) -> Optional[str]:
    for sp in sim_prompts:
        label = sp.get("label")
        rec = (pool.get("sims") or {}).get(label) or {}
        if rec.get("prep_status") == "pending":
            return label
    return None


def mark_prep_done(state: Dict[str, Any], sim_label: str) -> None:
    pool = state.get("hpc_pool") or {}
    rec = (pool.get("sims") or {}).get(sim_label)
    if rec:
        wd = rec.get("working_dir") or ""
        if not _sim_setup_ready(wd) and not _sim_trajectory_ready(wd):
            logger.warning(
                "HPC pool: refusing to mark prep done for %s — simsetup not ready",
                sim_label,
            )
            rec["prep_status"] = "pending"
            state["hpc_pool"] = pool
            return
        rec["prep_status"] = "done"
        if rec.get("hpc_status") == "pending" and _sim_production_trajectory_ready(wd):
            rec["hpc_status"] = "skipped"
            rec["skip_reason"] = "production trajectory on disk"
            rec.pop("job_id", None)
    state["hpc_pool"] = pool


def pool_hpc_phase_complete(state: Dict[str, Any]) -> bool:
    """True when the cross-sim HPC pool has finished (all jobs done or skipped)."""
    if state.get("hpc_pool_phase_complete"):
        return True
    pool = state.get("hpc_pool")
    if not pool:
        return False
    return _all_hpc_done(pool)


def reconcile_post_hpc_with_pool(state: Dict[str, Any]) -> bool:
    """
    Clear premature post-HPC routing when the HPC pool is not finished.

    Returns True when stale post-HPC state was cleared.
    """
    if not state.get("post_hpc_analysis_only"):
        return False
    if pool_hpc_phase_complete(state):
        return False
    logger.warning(
        "HPC pool still active — clearing stale post-HPC analysis state "
        "(per-sim analysis must wait until all pool jobs complete)"
    )
    state.pop("post_hpc_analysis_only", None)
    state.pop("hpc_pool_phase_complete", None)
    state["multi_sim_phase"] = "hpc_pool"
    state["plan_executed"] = False
    state["execution_plan"] = None
    state["input_validated"] = False
    state["current_agent_idx"] = 0
    return True


def start_post_hpc_phase(state: Dict[str, Any]) -> None:
    """Transition to per-sim analysis/reporter after all HPC jobs complete."""
    state["multi_sim_phase"] = "executing_sims"
    state["hpc_pool_phase_complete"] = True
    state["post_hpc_analysis_only"] = True
    state["subtask_type"] = "multi_agent"
    state["agent_list"] = ["analysis", "reporter"]
    state["plan_executed"] = False
    state["execution_plan"] = None
    state["input_validated"] = False
    state["enriched_prompt"] = None
    state.pop("hpc_pool_prep_only", None)
    state.pop("hpc_pool_agent_filter", None)
    pool = state.get("hpc_pool") or {}
    pool["phase"] = "complete"
    state["hpc_pool"] = pool
    from agentic.multi_sim_progress import reset_post_hpc_progress

    reset_post_hpc_progress(state)
    logger.info("HPC pool complete — starting post-HPC analysis/reporter loop")


def hpc_pool_supervisor_tick(state: Dict[str, Any]) -> Dict[str, Any]:
    """
    One supervisor iteration for ``multi_sim_phase == 'hpc_pool'``.

    Sets ``state['next_node']`` to supervisor, preprocess, setup, hpc_pool_wait,
    or human_hpc_pool_check.
    """
    pool = init_hpc_pool(state)

    if pool.get("awaiting_hitl"):
        state["next_node"] = "human_hpc_pool_check"
        state["hpc_pool_hitl_message"] = pool.get("hitl_reason") or "HPC pool needs attention"
        return state

    _sync_jobs_from_slurm(state, pool, force=False)
    pool = state["hpc_pool"]

    for label, rec in (pool.get("sims") or {}).items():
        if rec.get("hpc_status") == "failed":
            pool["awaiting_hitl"] = True
            pool["hitl_reason"] = rec.get("error") or f"Job failed for {label}"
            state["hpc_pool"] = pool
            state["next_node"] = "human_hpc_pool_check"
            return state

    # Phase 1: finish preprocess + simsetup for every simulation before any submit.
    prep_label = _next_prep_label(pool, state.get("sim_prompts") or [])
    if prep_label is not None:
        from agentic.parallel_resources import should_use_parallel_pool
        from agentic.multi_sim_parallel_pool import start_parallel_prep_if_enabled

        if should_use_parallel_pool(state) and not state.get("hpc_pool_prep_parallel"):
            if start_parallel_prep_if_enabled(state):
                return state
        state["hpc_pool_needs_prep_start"] = prep_label
        state["next_node"] = "supervisor"
        return state

    # Phase 2: all prep complete — submit/monitor HPC pool (up to max concurrent).
    _submit_ready_sims(state, pool)
    pool = state["hpc_pool"]

    if _all_hpc_done(pool):
        log_pool_to_base(state, "All HPC pool jobs complete — starting post-HPC analysis", pool=pool)
        start_post_hpc_phase(state)
        state["hpc_pool_post_hpc_start"] = True
        state["next_node"] = "supervisor"
        return state

    running = _count_running(pool)
    pending_submit = any(
        (r.get("prep_status") in ("done", "skipped") and r.get("hpc_status") == "pending")
        for r in (pool.get("sims") or {}).values()
    )
    if running > 0 or pending_submit:
        state["next_node"] = "hpc_pool_wait"
        state["hpc_pool_status_summary"] = pool_summary(state)
        log_pool_to_base(
            state,
            "Pool waiting for SLURM jobs",
            pool=pool,
            extra={"next_check_sec": pool.get("check_interval_sec")},
        )
        return state

    state["next_node"] = "hpc_pool_wait"
    return state


def pool_summary(state: Dict[str, Any]) -> str:
    pool = state.get("hpc_pool") or {}
    active = _count_running(pool)
    max_c = pool.get("max_concurrent", "?")
    lines = [
        f"HPC pool (active {active}/{max_c} concurrent, "
        f"check every {pool.get('check_interval_sec', '?')}s):"
    ]
    for label, rec in (pool.get("sims") or {}).items():
        parts = [
            f"prep={rec.get('prep_status')}",
            f"hpc={rec.get('hpc_status')}",
        ]
        if rec.get("job_id"):
            parts.append(f"job_id={rec.get('job_id')}")
        if rec.get("last_slurm_state"):
            parts.append(f"slurm={rec.get('last_slurm_state')}")
        if rec.get("skip_reason"):
            parts.append(f"note={rec.get('skip_reason')}")
        lines.append(f"  {label}: {' '.join(parts)}")
    return "\n".join(lines)


def resume_hpc_pool_if_needed(state: Dict[str, Any]) -> bool:
    """On ``--resume``, re-enter hpc_pool phase if jobs still active."""
    if state.get("multi_sim_phase") != "hpc_pool" and not state.get("hpc_pool"):
        return False
    pool = init_hpc_pool(state)
    if pool.get("phase") == "complete" or state.get("hpc_pool_phase_complete"):
        return False
    if _all_hpc_done(pool):
        start_post_hpc_phase(state)
        return True
    state["multi_sim_phase"] = "hpc_pool"
    _sync_jobs_from_slurm(state, pool, force=True)
    return True


def clear_hitl_pause(state: Dict[str, Any]) -> None:
    pool = state.get("hpc_pool") or {}
    pool["awaiting_hitl"] = False
    pool.pop("hitl_reason", None)
    for rec in (pool.get("sims") or {}).values():
        if rec.get("hpc_status") == "failed":
            rec["hpc_status"] = "pending"
            rec.pop("error", None)
    state["hpc_pool"] = pool
