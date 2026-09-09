"""Compact workflow state before writing state.jsonl (avoid huge arrays)."""
from __future__ import annotations

import copy
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Keys dropped entirely from persisted state (rebuilt from disk or logs if needed).
_OMIT_KEYS: Set[str] = {
    "execution_path",
    "_saved_workflow_status",
    "_saved_timestamp",
}

# Large string fields truncated to this many characters.
_TRUNCATE_STRINGS: Dict[str, int] = {
    "analysis_execution_log": 800,
    "analysis_report": 600,
    "hpc_report": 400,
    "setup_report": 400,
    "preprocessing_report": 400,
}

# Per-tool result keys worth keeping in analysis_results.
_ANALYSIS_KEEP_KEYS: Set[str] = {
    "success",
    "error",
    "message",
    "output_file",
    "output_files",
    "output_prefix",
    "mean_rmsf",
    "mean_rmsd",
    "mean_rg",
    "std_rmsf",
    "std_rg",
    "min_rmsf",
    "max_rmsf",
    "n_residues",
    "n_frames",
    "selection",
    "plot_file",
}

# List fields inside tool results — keep at most N items.
_ANALYSIS_LIST_LIMITS: Dict[str, int] = {
    "most_flexible": 5,
    "least_flexible": 5,
    "strong_pairs": 5,
}

# Drop these keys from nested analysis dicts (often hundreds/thousands of elements).
_ANALYSIS_DROP_KEYS: Set[str] = {
    "residue_ids",
    "residue_names",
    "correlation_matrix",
    "dccm_matrix",
    "matrix",
    "ss_percentages_per_frame",
    "distances",
    "time_series",
    "rmsf_values",
    "rg_values",
}

# Combined cross-sim block — keep file paths (small), not matrices.
_COMBINED_KEEP_KEYS: Set[str] = {
    "success",
    "error",
    "message",
    "analysis_dir",
    "com_distance_plot",
    "sim_dirs",
    "labels",
    "overlay_plots",
    "dccm_plots",
    "rmsf_apo_holo_plots",
    "rmsf_segment_plots",
    "dssp_plots",
    "stats_tables",
    "skipped_metrics",
    "apo_holo_pairs",
}
_COMBINED_LIST_PATH_LIMIT = 40

# Ephemeral per-sim fields omitted from multi-sim *base* checkpoints (live on disk per sim).
_BASE_MULTISIM_OMIT: Set[str] = {
    "execution_plan",
    "preprocessing_instructions",
    "setup_instructions",
    "hpc_instructions",
    "analysis_instructions",
    "reporter_instructions",
    "analysis_results",
    "analysis_report",
    "analysis_execution_log",
    "analysis_issues",
    "analysis_warnings",
    "enriched_prompt",
    "rephrased_goal",
    "reporter_output",
    "reporter_plan",
    "reporter_file_info",
    "figures",
    "file_registry",
    "generated_files",
    "file_info",
    "pdb_analysis",
    "component_selection",
    "structure_request",
    "structure_requests",
    "cleaned_pdb",
    "coordinates",
    "topology",
    "chain_residue_map",
    "trajectory_path",
    "energy_file",
    "job_id",
    "job_script",
    "job_status",
    "hpc_report",
    "setup_report",
    "preprocessing_report",
    "final_report",
    "analysis_directory",
    "analysis_dir",
    "preprocess_dir",
    "simsetup_dir",
    "hpc_dir",
    "reporter_dir",
}

_SIM_PROMPT_KEEP = frozenset({
    "label",
    "working_dir",
    "protein_name",
    "pdb",
    "pdb_path",
    "case_description",
})


def _compact_sim_prompts(prompts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for sp in prompts:
        if not isinstance(sp, dict):
            continue
        slim = {k: sp[k] for k in _SIM_PROMPT_KEEP if k in sp}
        if sp.get("label"):
            slim["label"] = sp["label"]
        if sp.get("working_dir"):
            slim["working_dir"] = sp["working_dir"]
        out.append(slim)
    return out


def _compact_completed_sim_states(states: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in states:
        if not isinstance(s, dict):
            continue
        out.append(
            {
                "label": s.get("label"),
                "working_directory": s.get("working_directory"),
                "success": s.get("success"),
                "skipped": s.get("skipped"),
                "sim_index": s.get("sim_index"),
            }
        )
    return out


def _compact_parallel_pool(pool: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not isinstance(pool, dict):
        return pool
    sims = pool.get("sims") or {}
    slim_sims = {}
    for label, rec in sims.items():
        if not isinstance(rec, dict):
            continue
        slim_sims[label] = {
            k: rec[k]
            for k in ("status", "working_dir", "error", "skip_reason", "started_at", "completed_at")
            if k in rec
        }
    return {
        "version": pool.get("version"),
        "phase": pool.get("phase"),
        "max_workers": pool.get("max_workers"),
        "resource_estimate": pool.get("resource_estimate"),
        "started_at": pool.get("started_at"),
        "sims": slim_sims,
    }


def _compact_combined_result(result: Dict[str, Any]) -> Dict[str, Any]:
    compact: Dict[str, Any] = {}
    for key in _COMBINED_KEEP_KEYS:
        if key not in result:
            continue
        val = result[key]
        if isinstance(val, list):
            paths = [str(x) for x in val if isinstance(x, (str, Path))]
            if paths:
                compact[key] = paths[:_COMBINED_LIST_PATH_LIMIT]
        elif isinstance(val, (str, bool, int, float)):
            compact[key] = val
    if "success" not in compact:
        compact["success"] = result.get("success", True)
    return compact


def _compact_analysis_result(result: Any, tool_name: str = "") -> Any:
    if tool_name == "combined" and isinstance(result, dict):
        return _compact_combined_result(result)
    if not isinstance(result, dict):
        return result
    compact: Dict[str, Any] = {}
    for key in _ANALYSIS_KEEP_KEYS:
        if key in result:
            compact[key] = result[key]
    for key, limit in _ANALYSIS_LIST_LIMITS.items():
        val = result.get(key)
        if isinstance(val, list) and val:
            compact[key] = val[:limit]
    if isinstance(result.get("ss_percentages"), dict):
        compact["ss_percentages"] = result["ss_percentages"]
    if not compact and result.get("message"):
        compact["message"] = str(result["message"])[:200]
    if "success" not in compact:
        compact["success"] = result.get("success", True)
    return compact


def compact_state_for_persistence(state: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of *state* safe to write to state.jsonl."""
    out = copy.deepcopy(state)
    for key in _OMIT_KEYS:
        out.pop(key, None)

    is_base_multisim = bool(
        state.get("is_multi_simulation")
        and (
            state.get("multi_sim_phase") in ("parallel_pool", "executing_sims", "combined_analysis", "combined_reporter", "hpc_pool")
            or state.get("parallel_pool")
            or len(state.get("sim_prompts") or []) > 1
        )
    )
    if is_base_multisim:
        for key in _BASE_MULTISIM_OMIT:
            out.pop(key, None)
        if out.get("completed_sim_states"):
            out["completed_sim_states"] = _compact_completed_sim_states(
                out["completed_sim_states"]
            )
        if out.get("sim_prompts"):
            out["sim_prompts"] = _compact_sim_prompts(out["sim_prompts"])
        if out.get("parallel_pool"):
            out["parallel_pool"] = _compact_parallel_pool(out["parallel_pool"])

    for key, limit in _TRUNCATE_STRINGS.items():
        val = out.get(key)
        if isinstance(val, str) and len(val) > limit:
            out[key] = val[:limit] + f"\n… [{len(val)} chars truncated for state file]"

    ar = out.get("analysis_results")
    if isinstance(ar, dict):
        out["analysis_results"] = {
            name: _compact_analysis_result(res, name) for name, res in ar.items()
        }

    figures = out.get("figures")
    if isinstance(figures, list) and len(figures) > 20:
        out["figures"] = figures[:20]
        out["figures_truncated"] = len(figures)

    registry = out.get("file_registry")
    if isinstance(registry, dict) and len(registry) > 40:
        keys = sorted(registry.keys())[:40]
        out["file_registry"] = {k: registry[k] for k in keys}
        out["file_registry_truncated"] = len(registry)

    return out


_AGENT_LADDER = ("preprocessing", "simsetup", "hpc", "analysis", "reporter")


def _normalize_agent_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    if text in ("completed", "complete", "skipped", "skip"):
        return "done"
    if text in ("submitted", "running"):
        return "in_progress"
    return text


def _sim_working_dir(state: Dict[str, Any], label: str, progress_rec: Optional[Dict[str, Any]]) -> str:
    wd = (progress_rec or {}).get("working_dir") or ""
    if wd:
        return str(wd)
    base = state.get("multi_sim_base_dir") or state.get("working_directory")
    if base and label:
        return str(Path(base) / label)
    return ""


def build_full_agent_ladder(
    state: Dict[str, Any],
    label: str,
    *,
    worker: Optional[str] = None,
    progress_rec: Optional[Dict[str, Any]] = None,
    hpc_rec: Optional[Dict[str, Any]] = None,
    pool_phase: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full per-sim agent ladder for ``pool_status.json``.

    Always includes preprocessing → simsetup → hpc → analysis → reporter.
    Upstream stages are marked ``done`` once later phases are active or disk
    artifacts prove completion.
    """
    from agentic.multi_sim_progress import (
        per_sim_analysis_done_on_disk,
        per_sim_reporter_done_on_disk,
    )

    progress = state.get("multi_sim_progress") or {}
    rec = progress_rec or ((progress.get("sims") or {}).get(label) or {})
    agents = dict(rec.get("agents") or {})
    wd = _sim_working_dir(state, label, rec)
    phase = pool_phase or (state.get("parallel_pool") or {}).get("phase")
    multi_phase = state.get("multi_sim_phase")

    ladder = {key: _normalize_agent_status(agents.get(key)) for key in _AGENT_LADDER}

    if hpc_rec:
        prep = _normalize_agent_status(hpc_rec.get("prep_status"))
        if prep == "done":
            ladder["preprocessing"] = "done"
            ladder["simsetup"] = "done"
        elif prep == "failed":
            if ladder["preprocessing"] != "done":
                ladder["preprocessing"] = "failed"
            ladder["simsetup"] = "failed"
        elif prep == "in_progress":
            if ladder["preprocessing"] not in ("done", "failed"):
                ladder["preprocessing"] = "in_progress"
            if ladder["simsetup"] not in ("done", "failed"):
                ladder["simsetup"] = "in_progress"
        elif prep == "pending":
            if not ladder["preprocessing"]:
                ladder["preprocessing"] = "pending"
            if not ladder["simsetup"]:
                ladder["simsetup"] = "pending"

        hpc_st = _normalize_agent_status(hpc_rec.get("hpc_status"))
        if hpc_st == "done":
            ladder["hpc"] = "done"
            ladder["preprocessing"] = "done"
            ladder["simsetup"] = "done"
        elif hpc_st == "failed":
            ladder["hpc"] = "failed"
        elif hpc_st == "in_progress":
            ladder["hpc"] = "in_progress"
            ladder["preprocessing"] = "done"
            ladder["simsetup"] = "done"
        elif hpc_st == "pending" and not ladder["hpc"]:
            ladder["hpc"] = "pending"

    if wd:
        root = Path(wd)
        preprocess_dir = root / "preprocess"
        simsetup_dir = root / "simsetup"
        hpc_dir = root / "hpc"
        # Real simsetup products (not merely a seeded reuse-hpc trajectory).
        simsetup_ready = simsetup_dir.is_dir() and (
            (simsetup_dir / "topol.top").is_file()
            or (simsetup_dir / "solvated.gro").is_file()
            or (simsetup_dir / "system.gro").is_file()
            or any(simsetup_dir.glob("*.top"))
        )
        preprocess_ready = preprocess_dir.is_dir() and (
            (preprocess_dir / "protein_h.pdb").is_file()
            or (preprocess_dir / "protein.pdb").is_file()
            or (preprocess_dir / "raw.pdb").is_file()
        )
        traj_seeded = hpc_dir.is_dir() and (hpc_dir / "md.tpr").is_file() and (
            (hpc_dir / "mdWrap.xtc").is_file() or (hpc_dir / "md.xtc").is_file()
        )
        # Authentic HPC-pool prep flag when available (do not infer from seed traj).
        prep_from_pool = (
            _normalize_agent_status((hpc_rec or {}).get("prep_status"))
            if hpc_rec
            else None
        )
        prep_complete = prep_from_pool == "done" or simsetup_ready

        if simsetup_ready:
            if ladder["preprocessing"] != "failed":
                ladder["preprocessing"] = "done"
            if ladder["simsetup"] != "failed":
                ladder["simsetup"] = "done"
        elif preprocess_ready:
            if not ladder["preprocessing"] or ladder["preprocessing"] == "pending":
                ladder["preprocessing"] = "done"

        # Seeded reuse-hpc campaigns place md.tpr+mdWrap.xtc in every sim dir
        # *before* preprocess/simsetup run. That must NOT mark prep/HPC done —
        # summary_lines (prep_status/hpc_status) are the source of truth mid-prep.
        if traj_seeded and prep_complete:
            if ladder["hpc"] != "failed":
                ladder["hpc"] = "done"
            if ladder["preprocessing"] != "failed":
                ladder["preprocessing"] = "done"
            if ladder["simsetup"] != "failed":
                ladder["simsetup"] = "done"
        elif traj_seeded and prep_from_pool == "pending":
            # Keep ladder honest while prep workers are still outstanding.
            if ladder["hpc"] not in ("done", "failed", "in_progress"):
                ladder["hpc"] = "pending"
            if ladder["preprocessing"] not in ("done", "failed", "in_progress"):
                ladder["preprocessing"] = "pending"
            if ladder["simsetup"] not in ("done", "failed", "in_progress"):
                ladder["simsetup"] = "pending"

        if per_sim_analysis_done_on_disk(wd):
            ladder["analysis"] = "done"
        if per_sim_reporter_done_on_disk(wd):
            ladder["analysis"] = "done"
            ladder["reporter"] = "done"

    # Reached analysis (or later) ⇒ upstream stages are complete unless failed.
    # Only apply this promotion when *this* sim's prep is done (or we are past
    # the HPC pool entirely). Global post_hpc flags used to mark every seeded
    # sim as prep-done while parallel prep was still running.
    past_hpc_globally = bool(
        state.get("hpc_pool_phase_complete") and not hpc_rec
    ) or (
        state.get("hpc_pool_phase_complete")
        and hpc_rec
        and _normalize_agent_status(hpc_rec.get("prep_status")) == "done"
    )
    if phase == "analysis" or multi_phase in (
        "combined_analysis",
        "combined_reporter",
        "complete",
    ) or past_hpc_globally:
        for key in ("preprocessing", "simsetup", "hpc"):
            if ladder[key] != "failed":
                ladder[key] = "done"
    elif multi_phase == "executing_sims" and (
        not hpc_rec
        or _normalize_agent_status((hpc_rec or {}).get("prep_status")) == "done"
    ):
        for key in ("preprocessing", "simsetup", "hpc"):
            if ladder[key] != "failed":
                ladder[key] = "done"

    # Prep parallel pool has not started analysis yet.
    if phase == "prep":
        if not ladder["analysis"]:
            ladder["analysis"] = "pending"
        if not ladder["reporter"]:
            ladder["reporter"] = "pending"

    for key in _AGENT_LADDER:
        if not ladder[key]:
            ladder[key] = "pending"

    status = _normalize_agent_status(rec.get("status")) or _normalize_agent_status(worker) or "pending"
    if status == "in_progress" and worker == "running":
        status = "in_progress"
    entry: Dict[str, Any] = {
        "preprocessing": ladder["preprocessing"],
        "simsetup": ladder["simsetup"],
        "hpc": ladder["hpc"],
        "analysis": ladder["analysis"],
        "reporter": ladder["reporter"],
        "status": status,
    }
    if worker is not None:
        entry["worker"] = worker
    if hpc_rec and hpc_rec.get("job_id"):
        entry["job_id"] = hpc_rec.get("job_id")
    if hpc_rec and hpc_rec.get("last_slurm_state"):
        entry["slurm"] = hpc_rec.get("last_slurm_state")
    if hpc_rec and hpc_rec.get("skip_reason"):
        entry["note"] = hpc_rec.get("skip_reason")
    if rec.get("error") or (hpc_rec or {}).get("error"):
        entry["error"] = rec.get("error") or (hpc_rec or {}).get("error")
    return entry


def build_pool_status_snapshot(state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Unified live status for ``pool_status.json`` across workflow stages.

    Covers parallel prep/analysis pools, HPC SLURM pool, sequential per-sim
    execution, and combined analysis/reporter. Every phase includes the full
    agent ladder per simulation.
    """
    if not state.get("is_multi_simulation"):
        return None

    phase = state.get("multi_sim_phase")
    hpc_pool = state.get("hpc_pool") or {}
    hpc_active = (
        phase == "hpc_pool"
        or (
            hpc_pool
            and hpc_pool.get("phase") != "complete"
            and not state.get("hpc_pool_phase_complete")
        )
    )

    if hpc_active:
        from agentic.multi_sim_hpc_pool import snapshot_hpc_pool_status

        snap = snapshot_hpc_pool_status(state)
        progress = state.get("multi_sim_progress") or {}
        pool_sims = (hpc_pool.get("sims") or {})
        labels = (
            list(progress.get("sim_order") or [])
            or list(snap.get("simulations") or {})
            or sorted(pool_sims.keys())
        )
        enriched = {}
        for label in labels:
            enriched[label] = build_full_agent_ladder(
                state,
                label,
                worker=((state.get("parallel_pool") or {}).get("sims") or {}).get(label, {}).get("status"),
                progress_rec=(progress.get("sims") or {}).get(label),
                hpc_rec=pool_sims.get(label),
                pool_phase="prep" if (state.get("parallel_pool") or {}).get("phase") == "prep" else None,
            )
        snap["simulations"] = enriched
        return snap

    parallel_pool = state.get("parallel_pool")
    if parallel_pool:
        from agentic.multi_sim_parallel_pool import init_parallel_pool

        init_parallel_pool(state, phase=parallel_pool.get("phase") or "analysis")

    if parallel_pool or phase == "parallel_pool":
        from agentic.multi_sim_parallel_pool import snapshot_parallel_pool_status
        from agentic.multi_sim_progress import sync_parallel_pool_to_multi_sim_progress

        sync_parallel_pool_to_multi_sim_progress(state)
        pool = state.get("parallel_pool") or parallel_pool
        if pool:
            snap = snapshot_parallel_pool_status(pool)
            snap["workflow_phase"] = phase or "parallel_pool"
            progress = state.get("multi_sim_progress") or {}
            hpc_sims = (state.get("hpc_pool") or {}).get("sims") or {}
            labels = (
                list(progress.get("sim_order") or [])
                or sorted((pool.get("sims") or {}).keys())
            )
            snap["simulations"] = {
                label: build_full_agent_ladder(
                    state,
                    label,
                    worker=(pool.get("sims") or {}).get(label, {}).get("status"),
                    progress_rec=(progress.get("sims") or {}).get(label),
                    hpc_rec=hpc_sims.get(label),
                    pool_phase=pool.get("phase"),
                )
                for label in labels
            }
            return snap

    if phase in ("executing_sims", "combined_analysis", "combined_reporter", "complete"):
        try:
            from agentic.multi_sim_progress import reconcile_multisim_progress_from_disk

            if state.get("multi_sim_progress") or state.get("sim_prompts"):
                reconcile_multisim_progress_from_disk(state)
        except Exception as exc:
            logger.debug("pool_status disk reconcile skipped: %s", exc)
        return _snapshot_from_multi_sim_progress(state)

    if state.get("hpc_pool_status_snapshot"):
        return dict(state["hpc_pool_status_snapshot"])
    if state.get("parallel_pool_status"):
        out = dict(state["parallel_pool_status"])
        out.setdefault("workflow_phase", phase)
        return out
    return None


def _snapshot_from_multi_sim_progress(state: Dict[str, Any]) -> Dict[str, Any]:
    from datetime import datetime, timezone

    from agentic.multi_sim_progress import load_local_continuation_job

    progress = state.get("multi_sim_progress") or {}
    sims = progress.get("sims") or {}
    hpc_sims = (state.get("hpc_pool") or {}).get("sims") or {}
    by_status: Dict[str, List[str]] = {
        "running": [],
        "pending": [],
        "done": [],
        "failed": [],
        "submitted": [],
    }
    sim_details: Dict[str, Any] = {}
    summary_lines: List[str] = []
    terminal_job = {
        "COMPLETED", "COMPLETE", "CANCELLED", "CANCELED", "FAILED",
        "TIMEOUT", "NODE_FAIL", "OUT_OF_MEMORY", "PREEMPTED",
    }

    for label in progress.get("sim_order") or sorted(sims.keys()):
        rec = sims.get(label) or {}
        wd = rec.get("working_dir") or ""
        job_info = load_local_continuation_job(wd) if wd else None
        job_id = (job_info or {}).get("job_id")
        job_status = str((job_info or {}).get("status") or "").upper()
        entry = build_full_agent_ladder(
            state,
            label,
            progress_rec=rec,
            hpc_rec=hpc_sims.get(label),
        )
        if job_id:
            entry["job_id"] = job_id
            entry["job_status"] = job_status or None

        # Prefer live continuation job truth over a stale pending progress row.
        st = entry.get("status") or "pending"
        if rec.get("status") == "failed" and not job_id:
            st = "failed"
            entry["status"] = "failed"
        elif job_info and job_info.get("complete"):
            st = "done"
            entry["hpc"] = "done"
            entry["status"] = "done"
        elif job_id and job_status not in terminal_job:
            st = "submitted"
            entry["hpc"] = "done"
            entry["status"] = "submitted"
        elif st == "in_progress":
            st = "running"

        sim_details[label] = entry

        parts = [f"status={entry.get('status') or st}"]
        for agent_key in _AGENT_LADDER:
            if entry.get(agent_key):
                parts.append(f"{agent_key}={entry[agent_key]}")
        if job_id:
            parts.append(f"job={job_id}")
            if job_status:
                parts.append(f"slurm={job_status}")
        summary_lines.append(f"  {label}: {' '.join(parts)}")

        if st == "submitted":
            by_status["submitted"].append(label)
            by_status["running"].append(label)
        else:
            bucket = st if st in ("running", "pending", "done", "failed") else "pending"
            by_status[bucket].append(label)

    workers = int(state.get("parallel_workers_resolved") or 0)
    pool_type = "parallel_analysis" if workers > 1 else "sequential"

    snap: Dict[str, Any] = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_phase": state.get("multi_sim_phase"),
        "pool_type": pool_type,
        "phase": progress.get("phase"),
        "max_workers": workers or None,
        "active_sim": progress.get("active_sim_label"),
        "active_agent": progress.get("active_agent"),
        "simulations": sim_details,
        "summary_lines": summary_lines,
        "running": sorted(set(by_status["running"])),
        "pending": sorted(by_status["pending"]),
        "done": sorted(by_status["done"]),
        "failed": sorted(by_status["failed"]),
        "submitted": sorted(by_status["submitted"]),
        "pending_count": len(by_status["pending"]),
        "done_count": len(by_status["done"]),
        "failed_count": len(by_status["failed"]),
        "submitted_count": len(by_status["submitted"]),
    }
    if progress.get("combined"):
        snap["combined"] = progress["combined"]
    return snap


def write_pool_status_json(state: Dict[str, Any], supervisor_dir: Path) -> None:
    """Write ``pool_status.json`` when multi-sim pool tracking is active."""
    pool_status = build_pool_status_snapshot(state)
    if pool_status:
        (supervisor_dir / "pool_status.json").write_text(
            json.dumps(pool_status, indent=2) + "\n",
            encoding="utf-8",
        )


def save_workflow_state_quiet(state: Dict[str, Any]) -> None:
    """Persist ``state.jsonl`` without updating execution_report.md (pool polls)."""
    import json
    from datetime import datetime

    from agentic.multi_sim_progress import ensure_multi_sim_progress, multisim_workflow_incomplete

    if state.get("is_multi_simulation") and state.get("sim_prompts"):
        ensure_multi_sim_progress(state)

    multi_base_dir = state.get("multi_sim_base_dir")
    working_dir = str(Path(str(multi_base_dir or state.get("working_directory", "."))).resolve())
    supervisor_dir = Path(working_dir) / "supervisor"
    supervisor_dir.mkdir(parents=True, exist_ok=True)
    state_path = supervisor_dir / "state.jsonl"

    snapshot = compact_state_for_persistence(dict(state))
    serializable_state = {}
    for key, value in snapshot.items():
        try:
            json.dumps(value, default=str)
            serializable_state[key] = value
        except (TypeError, ValueError):
            serializable_state[key] = str(value)

    persist_status = state.get("workflow_status", "unknown")
    if (
        state.get("is_multi_simulation")
        and persist_status == "completed"
        and multisim_workflow_incomplete(state.get("multi_sim_progress"))
    ):
        persist_status = "in_progress:interrupted"
    elif state.get("multi_sim_phase") == "parallel_pool":
        persist_status = "in_progress:parallel_pool"
    elif state.get("multi_sim_phase") == "hpc_pool":
        persist_status = "in_progress:hpc_pool"

    if state.get("is_multi_simulation") and multi_base_dir:
        serializable_state["working_directory"] = working_dir

    entry = {
        "timestamp": datetime.now().isoformat(),
        "workflow_status": persist_status,
        "state": serializable_state,
    }
    state_path.write_text(json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")

    write_pool_status_json(state, supervisor_dir)
