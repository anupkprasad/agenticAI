"""Campaign run memory: past errors and fixes, retrieved on the next failure.

Does not replace the compiled analysis protocol (CampaignSpec).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentic.retrieval.embed import hashed_ngram_embed, hybrid_score

logger = logging.getLogger(__name__)

MEMORY_NAME = "memory.jsonl"
MEMORY_SCHEMA = "1.0"


def memory_path(base_dir: str | Path) -> Path:
    return Path(base_dir) / "campaign" / MEMORY_NAME


def _campaign_base(state: Optional[Dict[str, Any]] = None) -> str:
    if not state:
        return ""
    return str(
        state.get("multi_sim_base_dir")
        or state.get("working_directory")
        or ""
    )


def remember_episode(
    *,
    base_dir: str | Path = "",
    state: Optional[Dict[str, Any]] = None,
    stage: str = "",
    error: str = "",
    fix: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Append one {stage, error, fix, embedding} record to campaign/memory.jsonl."""
    root = str(base_dir or _campaign_base(state) or "").strip()
    if not root or not (error or "").strip():
        return None
    text = f"{stage} {error} {fix}".strip()
    record = {
        "schema_version": MEMORY_SCHEMA,
        "timestamp": datetime.now().isoformat(),
        "stage": str(stage or "unknown"),
        "error": str(error)[:800],
        "fix": str(fix)[:800],
        "embedding": hashed_ngram_embed(text),
    }
    if extra:
        record["extra"] = {k: str(v)[:200] for k, v in extra.items()}
    path = memory_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
        logger.info("Run memory: recorded %s error at %s", stage, path)
        return path
    except OSError as exc:
        logger.debug("Run memory write failed: %s", exc)
        return None


def remember_from_state(
    state: Optional[Dict[str, Any]],
    *,
    stage: str,
    error: str,
    fix: str = "",
) -> Optional[Path]:
    return remember_episode(state=state, stage=stage, error=error, fix=fix)


def load_episodes(base_dir: str | Path) -> List[Dict[str, Any]]:
    path = memory_path(base_dir)
    if not path.is_file():
        return []
    out: List[Dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(rec, dict) and rec.get("error"):
                out.append(rec)
    except OSError:
        return []
    return out


def retrieve_episodes(
    query: str,
    *,
    base_dir: str | Path = "",
    state: Optional[Dict[str, Any]] = None,
    top_k: int = 5,
) -> List[Dict[str, Any]]:
    root = str(base_dir or _campaign_base(state) or "").strip()
    if not root:
        return []
    episodes = load_episodes(root)
    if not episodes:
        return []
    q = (query or "").strip() or "analysis error missing tool"
    q_vec = hashed_ngram_embed(q)
    scored: List[tuple[float, Dict[str, Any]]] = []
    for rec in episodes:
        blob = f"{rec.get('stage', '')} {rec.get('error', '')} {rec.get('fix', '')}"
        d_vec = rec.get("embedding") or hashed_ngram_embed(blob)
        scored.append((hybrid_score(q, blob, q_vec, d_vec), rec))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [rec for _, rec in scored[: max(1, int(top_k))]]


def format_episodes_for_prompt(episodes: List[Dict[str, Any]]) -> str:
    if not episodes:
        return ""
    lines = [
        "**Prior run notes** (errors and fixes from this campaign — do not repeat them):",
        "",
    ]
    for rec in episodes:
        stage = rec.get("stage") or "unknown"
        err = (rec.get("error") or "").replace("\n", " ")[:240]
        fix = (rec.get("fix") or "").replace("\n", " ")[:240]
        lines.append(f"- [{stage}] {err}")
        if fix:
            lines.append(f"  fix: {fix}")
    return "\n".join(lines).strip()


def retrieve_memory_for_prompt(
    state: Optional[Dict[str, Any]],
    query: str = "",
    *,
    top_k: int = 5,
) -> str:
    q = query or " ".join((state or {}).get("errors") or []) or "workflow error"
    hits = retrieve_episodes(q, state=state, top_k=top_k)
    return format_episodes_for_prompt(hits)
