"""Compact workflow state before writing state.jsonl (avoid huge arrays)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

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

    if state.get("is_multi_simulation") and multi_base_dir:
        serializable_state["working_directory"] = working_dir

    entry = {
        "timestamp": datetime.now().isoformat(),
        "workflow_status": persist_status,
        "state": serializable_state,
    }
    state_path.write_text(json.dumps(entry, indent=2, default=str) + "\n", encoding="utf-8")

    # Lightweight live status for ``tail`` / ``watch`` (does not grow like full state).
    pool_status = serializable_state.get("parallel_pool_status")
    if pool_status:
        (supervisor_dir / "pool_status.json").write_text(
            json.dumps(pool_status, indent=2) + "\n",
            encoding="utf-8",
        )
