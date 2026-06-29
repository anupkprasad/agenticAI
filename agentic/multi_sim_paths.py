"""Path helpers for multi-simulation orchestration."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict


def resolve_multi_sim_base_dir(state: Dict[str, Any]) -> str:
    """
    Canonical project base for combined analysis/reporter and pool logging.

    Prefer ``multi_sim_base_dir``; otherwise infer ``parent(sim_prompts[0].working_dir)``
    so per-sim ``working_directory`` does not hijack base-level outputs.
    """
    base = state.get("multi_sim_base_dir")
    if base:
        return str(Path(base).resolve())

    sim_prompts = state.get("sim_prompts") or []
    if sim_prompts:
        wd = (sim_prompts[0] or {}).get("working_dir")
        if wd:
            return str(Path(wd).parent.resolve())

    return str(Path(state.get("working_directory") or ".").resolve())
