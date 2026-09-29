"""Retrieve the top-k tools for a goal instead of dumping the full catalog."""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Sequence

from agentic.retrieval.catalog import catalog_from_registry
from agentic.retrieval.embed import hashed_ngram_embed, hybrid_score, ollama_embed

logger = logging.getLogger(__name__)

_DEFAULT_K = 16


class ToolRetriever:
    """Hybrid hashed-n-gram + lexical retrieval over the live tool catalog.

    Family-campaign pin tools are always included. Optional Ollama dense
    embeddings blend in when ``AGENTIC_EMBED_MODEL`` is set.
    """

    def __init__(self, registry: Any):
        self.registry = registry

    def retrieve(
        self,
        query: str,
        *,
        agent_name: Optional[str] = None,
        exclude_combined_tools: bool = False,
        top_k: int = _DEFAULT_K,
        pin_names: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        records = catalog_from_registry(
            self.registry,
            agent_name=agent_name,
            exclude_combined_tools=exclude_combined_tools,
        )
        if not records:
            return []
        if not (query or "").strip():
            return records[:top_k]

        q_vec = hashed_ngram_embed(query)
        scored: List[tuple[float, Dict[str, Any]]] = []
        dense = ollama_embed([query] + [r["embed_text"] for r in records])
        q_dense = dense[0] if dense else None
        d_dense = dense[1:] if dense else None

        for i, rec in enumerate(records):
            d_vec = hashed_ngram_embed(rec["embed_text"])
            score = hybrid_score(query, rec["embed_text"], q_vec, d_vec)
            if q_dense is not None and d_dense is not None:
                from agentic.retrieval.embed import cosine

                score = 0.55 * score + 0.45 * cosine(q_dense, d_dense[i])
            scored.append((score, rec))
        scored.sort(key=lambda x: x[0], reverse=True)

        picked: List[Dict[str, Any]] = []
        seen = set()
        for name in pin_names or []:
            for rec in records:
                if rec["name"] == name and rec["name"] not in seen:
                    picked.append(rec)
                    seen.add(rec["name"])
                    break
        for score, rec in scored:
            if rec["name"] in seen:
                continue
            picked.append(rec)
            seen.add(rec["name"])
            if len(picked) >= top_k:
                break
        logger.info(
            "ToolRetriever: query_chars=%d agent=%s pinned=%d returned=%d/%d names=%s",
            len(query or ""),
            agent_name,
            len(pin_names or []),
            len(picked),
            len(records),
            [r.get("name") for r in picked[:8]],
        )
        return picked


def format_retrieved_tools(records: Iterable[Dict[str, Any]], *, max_desc: int = 280) -> str:
    lines = [
        "RETRIEVED TOOLS (ranked for this goal — not the full catalog)",
        "",
    ]
    for rec in records:
        desc = (rec.get("description") or "").replace("\n", " ")
        if len(desc) > max_desc:
            desc = desc[: max_desc - 1] + "…"
        lines.append(f"- {rec.get('name')} [{rec.get('agent')}]: {desc}")
        tool = rec.get("tool") or {}
        params = tool.get("parameters") or {}
        if params:
            req = [k for k, v in params.items() if (v or {}).get("required")]
            if req:
                lines.append(f"    required: {', '.join(req)}")
        lines.append("")
    return "\n".join(lines).strip()


def retrieve_tools_for_prompt(
    registry: Any,
    query: str,
    *,
    agent_name: Optional[str] = None,
    exclude_combined_tools: bool = False,
    top_k: int = _DEFAULT_K,
    pin_names: Optional[Sequence[str]] = None,
    fallback_formatter=None,
) -> str:
    """Return a planner-ready tool subset, or the full catalog if retrieval is empty."""
    retriever = ToolRetriever(registry)
    records = retriever.retrieve(
        query,
        agent_name=agent_name,
        exclude_combined_tools=exclude_combined_tools,
        top_k=top_k,
        pin_names=pin_names,
    )
    if records:
        return format_retrieved_tools(records)
    if fallback_formatter:
        return fallback_formatter()
    return registry.get_tools_for_planner(
        agent_name,
        exclude_combined_tools=exclude_combined_tools,
    )
