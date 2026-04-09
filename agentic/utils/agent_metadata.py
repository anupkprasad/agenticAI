"""Agent metadata persistence.

Each field agent saves a ``agent_metadata.json`` file in its own directory
after execution.  This gives the HITL interactive handler (and subsequent
agents) rich, up-to-date context about what the agent did, what succeeded,
what failed, and any human recommendations received.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def save_agent_metadata(
    agent_dir: str,
    agent_name: str,
    *,
    success: bool,
    steps_executed: int = 0,
    steps_succeeded: int = 0,
    steps_failed: int = 0,
    issues: Optional[List[str]] = None,
    warnings: Optional[List[str]] = None,
    generated_files: Optional[List[str]] = None,
    key_outputs: Optional[Dict[str, Any]] = None,
    execution_log_tail: Optional[str] = None,
    human_recommendation: Optional[str] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Write ``agent_metadata.json`` into *agent_dir*.

    The file is overwritten on each call so it always reflects the latest
    execution of that agent.

    Returns the path to the written file, or ``None`` on error.
    """
    try:
        d = Path(agent_dir)
        d.mkdir(parents=True, exist_ok=True)
        meta_path = d / "agent_metadata.json"

        data: Dict[str, Any] = {
            "agent": agent_name,
            "timestamp": datetime.now().isoformat(),
            "success": success,
            "steps_executed": steps_executed,
            "steps_succeeded": steps_succeeded,
            "steps_failed": steps_failed,
            "issues": issues or [],
            "warnings": warnings or [],
            "generated_files": generated_files or [],
            "key_outputs": key_outputs or {},
        }

        if execution_log_tail:
            # Only keep last 3000 chars to avoid bloat
            data["execution_log_tail"] = execution_log_tail[-3000:]

        if human_recommendation:
            data["human_recommendation"] = human_recommendation

        if extra:
            data.update(extra)

        meta_path.write_text(
            json.dumps(data, indent=2, default=str), encoding="utf-8"
        )
        logger.info(f"Agent metadata saved to {meta_path}")
        return str(meta_path)

    except Exception as e:
        logger.error(f"Failed to save agent metadata for {agent_name}: {e}")
        return None


def load_agent_metadata(agent_dir: str) -> Optional[Dict[str, Any]]:
    """Load ``agent_metadata.json`` from *agent_dir*.

    Returns the parsed dict, or ``None`` if the file does not exist or is
    unreadable.
    """
    try:
        meta_path = Path(agent_dir) / "agent_metadata.json"
        if not meta_path.exists():
            return None
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Could not load agent metadata from {agent_dir}: {e}")
        return None
