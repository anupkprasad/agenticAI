"""Compact workflow state before writing state.jsonl (avoid huge arrays)."""
from __future__ import annotations

import copy
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
