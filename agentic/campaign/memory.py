"""Campaign run memory: past errors and fixes, retrieved on the next failure.

Does not replace the compiled analysis protocol (CampaignSpec).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentic.retrieval.embed import (
    blend_with_dense,
    dense_vectors,
    hashed_ngram_embed,
    hybrid_score,
)

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


def resolve_campaign_root(
    base_dir: str | Path = "",
    state: Optional[Dict[str, Any]] = None,
) -> str:
    """Directory that owns ``campaign/memory.jsonl``.

    Prefers the multi-sim campaign root over a per-protein folder so notes
    written from a simulation log are readable by the planner and reporter.
    """
    from_state = _campaign_base(state)
    ordered: List[Path] = []
    if from_state:
        ordered.append(Path(from_state))
    raw = str(base_dir or "").strip()
    if raw:
        here = Path(raw)
        ordered.append(here)
        ordered.append(here.parent)
    for cand in ordered:
        if not str(cand):
            continue
        if (cand / "labels.txt").is_file() or (cand / "goal.txt").is_file():
            return str(cand)
        if (cand / "campaign").is_dir() and not (cand.parent / "labels.txt").is_file():
            return str(cand)
    if from_state:
        return from_state
    return raw


def _episode_key(record: Dict[str, Any]) -> str:
    stage = str(record.get("stage") or "")
    tool = str(record.get("tool") or "")
    err = " ".join(str(record.get("error") or "").lower().split())[:180]
    return f"{stage}|{tool}|{err}"


def _write_episodes(path: Path, episodes: List[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(rec, default=str) + "\n" for rec in episodes)
    path.write_text(text, encoding="utf-8")


def remember_episode(
    *,
    base_dir: str | Path = "",
    state: Optional[Dict[str, Any]] = None,
    stage: str = "",
    error: str = "",
    fix: str = "",
    tool: str = "",
    label: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Optional[Path]:
    """Record one error at the campaign root.

    The same stage + tool + error text updates the existing episode instead of
    appending another copy. A later fix fills that episode.
    """
    root = resolve_campaign_root(base_dir, state)
    if not root or not (error or "").strip():
        return None
    text = f"{stage} {tool} {label} {error} {fix}".strip()
    record = {
        "schema_version": MEMORY_SCHEMA,
        "timestamp": datetime.now().isoformat(),
        "stage": str(stage or "unknown"),
        "tool": str(tool or "")[:120],
        "label": str(label or "")[:120],
        "error": str(error)[:800],
        "fix": str(fix)[:800],
        "embedding": hashed_ngram_embed(text),
    }
    if extra:
        record["extra"] = {k: str(v)[:200] for k, v in extra.items()}
    path = memory_path(root)
    try:
        episodes = load_episodes(root)
        key = _episode_key(record)
        replaced = False
        for old in episodes:
            if _episode_key(old) != key:
                continue
            if fix and not old.get("fix"):
                old["fix"] = record["fix"]
            if label and not old.get("label"):
                old["label"] = record["label"]
            if tool and not old.get("tool"):
                old["tool"] = record["tool"]
            old["timestamp"] = record["timestamp"]
            replaced = True
            break
        if not replaced:
            episodes.append(record)
        _write_episodes(path, episodes)
        logger.info("Run memory: recorded %s error at %s", stage, path)
        return path
    except OSError as exc:
        logger.debug("Run memory write failed: %s", exc)
        return None


def record_fix(
    state: Optional[Dict[str, Any]],
    *,
    stage: str,
    fix: str,
    base_dir: str | Path = "",
) -> Optional[Path]:
    """Fill the latest open episode for ``stage`` after a later success."""
    root = resolve_campaign_root(base_dir, state)
    note = (fix or "").strip()
    if not root or not note:
        return None
    episodes = load_episodes(root)
    target = None
    for rec in episodes:
        if str(rec.get("stage") or "") == stage and not (rec.get("fix") or "").strip():
            target = rec
    if target is None:
        return None
    target["fix"] = note[:800]
    target["timestamp"] = datetime.now().isoformat()
    path = memory_path(root)
    try:
        _write_episodes(path, episodes)
        return path
    except OSError as exc:
        logger.debug("Run memory fix write failed: %s", exc)
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
    root = resolve_campaign_root(base_dir, state)
    if not root:
        return []
    episodes = load_episodes(root)
    if not episodes:
        return []
    q = (query or "").strip() or "analysis error missing tool"
    q_vec = hashed_ngram_embed(q)
    blobs = [
        f"{rec.get('stage', '')} {rec.get('tool', '')} {rec.get('label', '')} "
        f"{rec.get('error', '')} {rec.get('fix', '')}"
        for rec in episodes
    ]
    dense = dense_vectors([q] + blobs)
    q_dense = dense[0] if dense else None
    scored: List[tuple[float, Dict[str, Any]]] = []
    for i, rec in enumerate(episodes):
        blob = blobs[i]
        d_vec = rec.get("embedding") or hashed_ngram_embed(blob)
        score = hybrid_score(q, blob, q_vec, d_vec)
        doc_dense = dense[i + 1] if i + 1 < len(dense) else None
        scored.append((blend_with_dense(score, q_dense, doc_dense), rec))
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
        tool = rec.get("tool") or ""
        label = rec.get("label") or ""
        err = (rec.get("error") or "").replace("\n", " ")[:240]
        fix = (rec.get("fix") or "").replace("\n", " ")[:240]
        where = " ".join(p for p in (label, tool) if p)
        prefix = f"{stage}" + (f" {where}" if where else "")
        lines.append(f"- [{prefix}] {err}")
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
