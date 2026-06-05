"""
Persist planner/programmer plans to working_dir/{agent_name}/.

Writes the latest plan as JSON + Markdown and appends each run to a JSONL history.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def ensure_agent_dir(working_dir: str, agent_name: str) -> Path:
    """Create and return {working_dir}/{agent_name}/."""
    agent_dir = Path(working_dir).resolve() / agent_name
    agent_dir.mkdir(parents=True, exist_ok=True)
    return agent_dir


def append_plan_entry(agent_dir: Path, history_filename: str, entry: Dict[str, Any]) -> None:
    """Append one plan record to a JSONL history file."""
    history_path = agent_dir / history_filename
    with open(history_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=str) + "\n")


def save_plan_artifacts(
    working_dir: str,
    agent_name: str,
    *,
    json_filename: str,
    md_filename: str,
    history_filename: str,
    plan_data: Dict[str, Any],
    md_content: str,
    phase: Optional[str] = None,
    label: Optional[str] = None,
) -> Optional[Path]:
    """
    Save plan JSON, Markdown, and append to JSONL history.

    Returns the agent directory path, or None on failure.
    """
    try:
        agent_dir = ensure_agent_dir(working_dir, agent_name)
        timestamp = datetime.now().isoformat()

        plan_data = dict(plan_data)
        plan_data.setdefault("timestamp", timestamp)
        if phase:
            plan_data["phase"] = phase
        if label:
            plan_data["label"] = label

        json_path = agent_dir / json_filename
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(plan_data, f, indent=2, default=str)

        md_path = agent_dir / md_filename
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        history_entry = {
            "timestamp": timestamp,
            "phase": phase,
            "label": label,
            "working_directory": str(Path(working_dir).resolve()),
            "json_file": json_filename,
            "md_file": md_filename,
            "title": plan_data.get("title") or plan_data.get("overview"),
        }
        append_plan_entry(agent_dir, history_filename, history_entry)

        logger.info(
            f"Saved {agent_name} plan to {agent_dir} "
            f"({json_filename}, {md_filename}, +{history_filename})"
        )
        return agent_dir
    except Exception as exc:
        logger.warning(f"Failed to save {agent_name} plan to {working_dir}: {exc}")
        return None
