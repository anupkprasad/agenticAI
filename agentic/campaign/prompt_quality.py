"""Reject LLM per-sim prompts that drop the shared scientific intent."""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Sequence

_TRUNCATION_MARKERS = (
    r"\(\s*same as above\s*\)",
    r"\bsame as above\b",
    r"\bas above\b",
    r"\bsee above\b",
    r"\bidem\b",
    r"\bditto\b",
    r"\.\.\.\s*$",
)

_FAMILY_SIGNAL = (
    r"consensus",
    r"dccm",
    r"rmsf",
    r"chi\s*1",
    r"χ",
    r"entropy",
    r"pocket",
    r"dihedral",
    r"orientation",
    r"axis",
)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def prompt_is_truncated(text: str) -> bool:
    """True when the LLM abbreviated a later sim with 'same as above' etc."""
    blob = _norm(text)
    if not blob:
        return True
    return any(re.search(p, blob) for p in _TRUNCATION_MARKERS)


def count_family_signals(text: str) -> int:
    blob = _norm(text)
    return sum(1 for p in _FAMILY_SIGNAL if re.search(p, blob))


def llm_sim_prompts_lose_shared_intent(
    sim_prompts: Optional[Sequence[str]],
    *,
    original_goal: str = "",
    family_modular: bool = False,
    min_chars: int = 200,
) -> bool:
    """True if any LLM per-sim prompt is truncated or lost the campaign science.

    Used to discard an LLM ``sim_prompts`` list even when its length matches N.
    """
    prompts = [str(p or "") for p in (sim_prompts or [])]
    if not prompts:
        return True
    if any(prompt_is_truncated(p) for p in prompts):
        return True

    lengths = [len(p.strip()) for p in prompts]
    if lengths and min(lengths) < max(min_chars, int(0.45 * max(lengths))):
        # Later prompts collapsed relative to the first detailed ones.
        if min(lengths) < 0.7 * (sum(lengths) / len(lengths)):
            return True

    if family_modular or count_family_signals(original_goal) >= 4:
        required = max(3, count_family_signals(original_goal) // 2)
        if any(count_family_signals(p) < required for p in prompts):
            return True
    return False


def shared_intent_excerpt(original_goal: str, *, max_chars: int = 1200) -> str:
    """Keep the scientific clauses of the master goal for every sim prompt."""
    text = (original_goal or "").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rsplit(" ", 1)[0] + "…"
