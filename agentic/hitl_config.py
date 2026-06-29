"""Human-in-the-loop (HITL) mode helpers."""
from typing import Optional, Tuple

from .state import MDState


def resolve_hitl_from_cli(hitl: Optional[str]) -> Tuple[bool, Optional[str]]:
    """Map ``--HITL`` CLI value to ``(human_in_loop, hitl_mode)``."""
    if not hitl:
        return False, None
    mode = hitl.strip().lower()
    if mode not in ("error", "all"):
        raise ValueError(f"Invalid --HITL mode: {hitl!r} (expected 'error' or 'all')")
    return True, mode


def hitl_should_interact(state: MDState) -> bool:
    """Return True when a checkpoint should pause for human input."""
    if not state.get("human_in_loop"):
        return False
    mode = (state.get("hitl_mode") or "all").strip().lower()
    if mode == "error":
        pool = state.get("hpc_pool") or {}
        if pool.get("awaiting_hitl"):
            return True
        return bool(state.get("error_triggered_hitl"))
    return True
