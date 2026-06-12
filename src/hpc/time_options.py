"""
Resolve SLURM walltime limits from user goals and framework defaults.

SLURM format: days-hours:minutes:seconds (e.g. ``5-00:00:00`` for five days).
"""
import re
from typing import Any, Dict, Optional

DEFAULT_SLURM_TIME_LIMIT = "5-00:00:00"

_SLURM_DAYS_RE = re.compile(r"^\d+-\d{2}:\d{2}:\d{2}$")
_SLURM_HOURS_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})$")

_DAYS_GOAL_RE = re.compile(
    r"(?:wall\s*time|hpc\s*time|time\s*limit|job\s*time)"
    r"(?:\s*(?:of|=|:))?\s*(\d+(?:\.\d+)?)\s*days?\b",
    re.IGNORECASE,
)
_DAYS_SIMPLE_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*days?\b",
    re.IGNORECASE,
)
_HOURS_GOAL_RE = re.compile(
    r"(?:wall\s*time|hpc\s*time|time\s*limit|job\s*time)"
    r"(?:\s*(?:of|=|:))?\s*(\d+)\s*hours?\b",
    re.IGNORECASE,
)


def _combined_goal_text(state: Optional[Dict[str, Any]] = None, user_text: str = "") -> str:
    state = state or {}
    parts = [
        user_text,
        state.get("user_goal"),
        state.get("user_goal_original"),
        state.get("enriched_prompt"),
        state.get("master_enriched_prompt"),
        state.get("hpc_instructions"),
    ]
    return "\n".join(p for p in parts if p)


def normalize_slurm_time(value: str) -> Optional[str]:
    """Normalize SLURM time strings; convert ``48:00:00`` to ``2-00:00:00``."""
    if not value:
        return None
    cleaned = str(value).strip()
    if _SLURM_DAYS_RE.match(cleaned):
        return cleaned
    hours_match = _SLURM_HOURS_RE.match(cleaned)
    if hours_match:
        total_hours = int(hours_match.group(1))
        minutes = hours_match.group(2)
        seconds = hours_match.group(3)
        days = total_hours // 24
        rem_hours = total_hours % 24
        return f"{days}-{rem_hours:02d}:{minutes}:{seconds}"
    return None


def format_days_as_slurm_time(days: float) -> str:
    days_int = max(0, int(days))
    return f"{days_int}-00:00:00"


def parse_walltime_from_text(text: str = "") -> Optional[str]:
    """Parse explicit walltime requests from natural-language goal text."""
    if not text:
        return None

    match = _DAYS_GOAL_RE.search(text)
    if match:
        return format_days_as_slurm_time(float(match.group(1)))

    match = _HOURS_GOAL_RE.search(text)
    if match:
        hours = int(match.group(1))
        days = hours // 24
        rem = hours % 24
        return f"{days}-{rem:02d}:00:00"

    # Bare "2 days" only when goal also mentions HPC / SLURM / submit context
    if re.search(r"\b(?:hpc|slurm|sbatch|wall\s*time|submit)\b", text, re.I):
        match = _DAYS_SIMPLE_RE.search(text)
        if match:
            return format_days_as_slurm_time(float(match.group(1)))

    return None


def resolve_hpc_time_limit(
    state: Optional[Dict[str, Any]] = None,
    user_text: str = "",
    proposed: Optional[str] = None,
    estimate_slurm_time: Optional[str] = None,
) -> str:
    """
    Pick SLURM ``--time`` with priority:
      1. state ``hpc_time_limit`` / parsed user goal (explicit user request)
      2. Valid normalized ``proposed`` from planner/estimate step
      3. Stored estimate from ``estimate_simulation_time``
      4. ``DEFAULT_SLURM_TIME_LIMIT`` (5 days)
    """
    state = state or {}

    if state.get("hpc_time_limit"):
        normalized = normalize_slurm_time(str(state["hpc_time_limit"]))
        if normalized:
            return normalized

    parsed = parse_walltime_from_text(_combined_goal_text(state, user_text))
    if parsed:
        return parsed

    if proposed:
        normalized = normalize_slurm_time(proposed)
        if normalized:
            return normalized

    estimate = estimate_slurm_time or state.get("estimated_slurm_time")
    if estimate:
        normalized = normalize_slurm_time(str(estimate))
        if normalized:
            return normalized

    return DEFAULT_SLURM_TIME_LIMIT


def apply_goal_hpc_time_config(goal: str, config: Dict[str, Any]) -> None:
    """Store parsed walltime on run_agenticAIWork config when the goal specifies it."""
    parsed = parse_walltime_from_text(goal)
    if parsed:
        config["hpc_time_limit"] = parsed
