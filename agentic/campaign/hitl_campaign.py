"""Review pauses after the compiled protocol and after combined stages."""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def request_compile_review(state: Dict[str, Any]) -> None:
    """Ask for a human review of the compiled protocol when HITL is 'all'."""
    if not state.get("human_in_loop"):
        return
    if (state.get("hitl_mode") or "").strip().lower() != "all":
        return
    if not state.get("campaign_spec"):
        return
    state["hitl_pause_after_compile"] = True
    state["hitl_checkpoint_subtype"] = "compile"
    logger.info("HITL: will pause after compiled analysis protocol")


def route_compile_review(state: Dict[str, Any]) -> bool:
    """If a compile review is pending, send the run to the analysis checkpoint."""
    if not state.get("hitl_pause_after_compile"):
        return False
    try:
        from agentic.hitl_router import bind_combined_hitl_view

        bind_combined_hitl_view(state, "analysis")
    except Exception:
        pass
    state["hitl_checkpoint_subtype"] = "compile"
    state["next_node"] = "human_analysis_check"
    logger.info("HITL: pausing for compiled-protocol review")
    return True


def continue_campaign_checkpoint(state: Dict[str, Any], checkpoint_type: str) -> bool:
    """Handle continue/approved for compile, pre-combined, and post-combined.

    Returns True if this function set next_node (caller should return).
    """
    subtype = str(state.get("hitl_checkpoint_subtype") or "")
    phase = str(state.get("multi_sim_phase") or "")

    if subtype == "compile" or state.get("hitl_pause_after_compile"):
        state.pop("hitl_pause_after_compile", None)
        state.pop("hitl_checkpoint_subtype", None)
        state["next_node"] = "supervisor"
        logger.info("HITL continue: compiled protocol approved → supervisor")
        return True

    if subtype == "pre_combined" or phase == "pre_combined":
        if checkpoint_type != "analysis":
            return False
        state.pop("hitl_checkpoint_subtype", None)
        # Supervisor sees pre_combined done on disk and starts per-sim work.
        state["next_node"] = "supervisor"
        logger.info("HITL continue: shared mapping/MSA approved → supervisor")
        return True

    if subtype == "post_combined":
        # Fall through to the existing combined_analysis → reporter path.
        return False

    return False
