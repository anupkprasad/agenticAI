"""Short notes from this study, retrieved like other knowledge.

Notes are task-agnostic: a label, the stage, and whatever numeric summaries
the analysis summary already recorded. They are not a kinase feature schema.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentic.campaign.memory import resolve_campaign_root
from agentic.retrieval.embed import (
    blend_with_dense,
    dense_vectors,
    hashed_ngram_embed,
    hybrid_score,
)

logger = logging.getLogger(__name__)

NOTES_NAME = "study_notes.jsonl"


def notes_path(base_dir: str | Path) -> Path:
    return Path(base_dir) / "campaign" / NOTES_NAME


def _numeric_bits(stats: Dict[str, Any], limit: int = 8) -> str:
    parts: List[str] = []
    for key, val in stats.items():
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            continue
        parts.append(f"{key}={val:.4g}" if isinstance(val, float) else f"{key}={val}")
        if len(parts) >= limit:
            break
    return ", ".join(parts)


def summarize_analysis_dir(analysis_dir: str | Path, *, label: str = "") -> str:
    """One paragraph from analysis_summary.jsonl. Empty when the file is absent."""
    path = Path(analysis_dir) / "analysis_summary.jsonl"
    if not path.is_file():
        return ""
    lines: List[str] = []
    try:
        raw_lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    for raw in raw_lines[-12:]:
        if not raw.strip():
            continue
        try:
            rec = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if not isinstance(rec, dict):
            continue
        kind = str(rec.get("analysis_type") or rec.get("tool") or "analysis")
        stats = rec.get("statistics") if isinstance(rec.get("statistics"), dict) else {}
        bits = _numeric_bits(stats)
        lines.append(f"{kind}: {bits}" if bits else kind)
    if not lines:
        return ""
    who = label or Path(analysis_dir).parent.name
    return f"{who}: " + "; ".join(lines)


def record_study_note(
    state: Optional[Dict[str, Any]],
    *,
    stage: str,
    summary: str,
    label: str = "",
    base_dir: str | Path = "",
) -> Optional[Path]:
    text = " ".join((summary or "").split())
    if not text:
        return None
    root = resolve_campaign_root(base_dir, state)
    if not root:
        return None
    record = {
        "timestamp": datetime.now().isoformat(),
        "stage": str(stage or "analysis"),
        "label": str(label or "")[:120],
        "summary": text[:1200],
        "embedding": hashed_ngram_embed(f"{stage} {label} {text}"),
    }
    path = notes_path(root)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
        return path
    except OSError as exc:
        logger.debug("study note write failed: %s", exc)
        return None


def load_notes(base_dir: str | Path) -> List[Dict[str, Any]]:
    path = notes_path(base_dir)
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
            if isinstance(rec, dict) and rec.get("summary"):
                out.append(rec)
    except OSError:
        return []
    return out


def retrieve_study_notes(
    query: str,
    *,
    state: Optional[Dict[str, Any]] = None,
    base_dir: str | Path = "",
    top_k: int = 4,
) -> List[Dict[str, Any]]:
    root = resolve_campaign_root(base_dir, state)
    if not root:
        return []
    notes = load_notes(root)
    if not notes:
        return []
    q = (query or "").strip() or "simulation analysis results"
    q_vec = hashed_ngram_embed(q)
    blobs = [
        f"{n.get('stage', '')} {n.get('label', '')} {n.get('summary', '')}"
        for n in notes
    ]
    dense = dense_vectors([q] + blobs)
    q_dense = dense[0] if dense else None
    scored: List[tuple] = []
    for i, note in enumerate(notes):
        d_vec = note.get("embedding") or hashed_ngram_embed(blobs[i])
        score = hybrid_score(q, blobs[i], q_vec, d_vec)
        doc_dense = dense[i + 1] if i + 1 < len(dense) else None
        scored.append((blend_with_dense(score, q_dense, doc_dense), note))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [note for _, note in scored[: max(1, int(top_k))]]


def format_study_notes(notes: List[Dict[str, Any]]) -> str:
    if not notes:
        return ""
    lines = ["**This study** (numeric notes already written for these systems):", ""]
    for note in notes:
        label = note.get("label") or note.get("stage") or "system"
        summary = (note.get("summary") or "").replace("\n", " ")[:400]
        lines.append(f"- {label}: {summary}")
    return "\n".join(lines).strip()
