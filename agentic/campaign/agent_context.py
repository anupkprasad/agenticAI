"""Per-agent retrieval block declared in campaign.yaml.

Analysis, reporter, and supervisor each get knowledge chunks, run-memory
episodes, and this study's notes. The block is empty when nothing matches,
so generic and family campaigns share the same call.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_PROFILE: Dict[str, Any] = {
    "knowledge_k": 4,
    "memory_k": 4,
    "study_k": 4,
}


def agent_profile(state: Optional[Dict[str, Any]], agent: str) -> Dict[str, Any]:
    from agentic.campaign.config import settings_from_state

    settings = settings_from_state(state)
    table = settings.agent_retrieval or {}
    raw = table.get(agent) if isinstance(table, dict) else None
    profile = dict(_DEFAULT_PROFILE)
    if isinstance(raw, dict):
        profile.update(raw)
    return profile


def agent_context_block(
    state: Optional[Dict[str, Any]],
    agent: str,
    query: str = "",
) -> str:
    """Text to prepend to an agent prompt. Safe to call when retrieval is empty."""
    profile = agent_profile(state, agent)
    q = (query or "").strip()
    if not q and state:
        bits = [
            str(state.get("user_goal_original") or ""),
            str(state.get("user_goal") or ""),
            " ".join(str(e) for e in (state.get("errors") or [])[:3]),
        ]
        q = " ".join(b for b in bits if b).strip()
    q = q[:1500] or "molecular dynamics simulation analysis report"
    parts = []
    try:
        from agentic.planner.knowledge_loader import get_knowledge_loader

        k = max(1, int(profile.get("knowledge_k") or 4))
        knowledge = get_knowledge_loader().get_knowledge_for_planner(
            query=q,
            top_k=k,
            max_chars=2800,
        )
        if knowledge and not knowledge.startswith("No knowledge"):
            parts.append(knowledge.strip())
    except Exception as exc:
        logger.debug("knowledge retrieval for %s skipped: %s", agent, exc)
    try:
        from agentic.campaign.memory import retrieve_memory_for_prompt

        memory = retrieve_memory_for_prompt(
            state,
            q,
            top_k=max(1, int(profile.get("memory_k") or 4)),
        )
        if memory:
            parts.append(memory)
    except Exception as exc:
        logger.debug("memory retrieval for %s skipped: %s", agent, exc)
    try:
        from agentic.campaign.study_notes import format_study_notes, retrieve_study_notes

        notes = retrieve_study_notes(
            q,
            state=state,
            top_k=max(1, int(profile.get("study_k") or 4)),
        )
        formatted = format_study_notes(notes)
        if formatted:
            parts.append(formatted)
    except Exception as exc:
        logger.debug("study-note retrieval for %s skipped: %s", agent, exc)
    if not parts:
        return ""
    body = "\n\n".join(parts)
    return (
        f"**Retrieved context for {agent}** "
        "(knowledge, earlier errors in this campaign, and notes from this study):\n\n"
        + body
    )
