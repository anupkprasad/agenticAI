"""Supervisor destination chosen by the model from a config policy.

The graph still accepts only the destinations listed in campaign.yaml.
When the model is unavailable, the existing next_node is left unchanged.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_DESTINATIONS = ("analysis", "reporter", "final_report")


def _profile(state: Dict[str, Any]) -> Dict[str, Any]:
    from agentic.campaign.agent_context import agent_profile

    return agent_profile(state, "supervisor")


def _active_label(state: Dict[str, Any]) -> str:
    progress = state.get("multi_sim_progress") or {}
    if isinstance(progress, dict):
        label = progress.get("active_sim_label") or ""
        if label:
            return str(label)
    return str(state.get("sim_label") or state.get("working_directory") or "campaign")


def _analysis_error(state: Dict[str, Any]) -> str:
    errors = state.get("errors") or []
    hits = [str(e) for e in errors if "analysis" in str(e).lower()]
    if hits:
        return hits[-1][:800]
    return ""


def maybe_apply_route_policy(state: Dict[str, Any], llm: Any) -> Dict[str, Any]:
    """If the next node is final_report after an analysis error, ask the model once.

    ``campaign.yaml`` ``agent_retrieval.supervisor.allowed_destinations`` is the
    only set the model may pick. One decision per system label.
    """
    if state.get("next_node") != "final_report":
        return state
    profile = _profile(state)
    if profile.get("route_once") is False:
        return state
    error = _analysis_error(state)
    if not error:
        return state
    label = _active_label(state)
    used = list(state.get("_route_policy_labels") or [])
    if label in used:
        return state
    destinations = profile.get("allowed_destinations") or list(_DEFAULT_DESTINATIONS)
    allowed = [str(d) for d in destinations if str(d) in _DEFAULT_DESTINATIONS]
    if not allowed:
        allowed = list(_DEFAULT_DESTINATIONS)
    used.append(label)
    state["_route_policy_labels"] = used

    from agentic.campaign.agent_context import agent_context_block

    query = f"{error} {state.get('user_goal_original') or state.get('user_goal') or ''}"
    context = agent_context_block(state, "supervisor", query=query[:1200])
    retries = int(state.get("analysis_retry_count") or 0)
    prompt = f"""You route one molecular-dynamics workflow step.

An analysis step reported an error. Choose the next destination.
Allowed destinations: {', '.join(allowed)}

- analysis: the measurements should be tried again, and this system has not already been retried
- reporter: write the report, including what is missing
- final_report: the study is finished

Retries already used for this analysis: {retries}
System: {label}
Error: {error[:600]}

{context[:2500]}

Return JSON only: {{"destination": "<one allowed name>", "reason": "<one sentence>"}}
"""
    destination = ""
    if llm is not None and getattr(llm, "available", False):
        try:
            if hasattr(llm, "set_agent"):
                llm.set_agent("supervisor")
            raw = llm.prompt_raw(prompt, temperature=0.1, max_tokens=300, format="json")
            destination = _parse_destination(raw, allowed)
        except Exception as exc:
            logger.info("Route policy model call failed: %s", exc)
    if destination and destination != "final_report":
        logger.info(
            "Route policy: %s -> %s after analysis error", label, destination
        )
        state["next_node"] = destination
        state["plan_executed"] = False
        if destination == "analysis":
            state["analysis_retry_count"] = retries + 1
            state["_route_policy_force"] = "analysis"
    return state


def _parse_destination(raw: str, allowed: List[str]) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            return ""
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return ""
    if not isinstance(data, dict):
        return ""
    dest = str(data.get("destination") or "").strip()
    return dest if dest in allowed else ""
