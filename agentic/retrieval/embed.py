"""Fast local embeddings for tool retrieval.

Default: stable hashed character n-grams (no extra model, deterministic).
Optional: Ollama ``/api/embeddings`` when ``AGENTIC_EMBED_MODEL`` is set and
the server is reachable.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
from functools import lru_cache
from typing import Dict, Iterable, List, Optional, Sequence

logger = logging.getLogger(__name__)

_DEFAULT_DIM = 256
_NGRAM = 3


def normalize_text(text: str) -> str:
    return " ".join((text or "").lower().replace("_", " ").split())


@lru_cache(maxsize=4096)
def hashed_ngram_embed(
    text: str,
    dim: int = _DEFAULT_DIM,
    n: int = _NGRAM,
) -> List[float]:
    """Signed hashed n-gram bag, L2-normalised. Stable across processes."""
    blob = normalize_text(text)
    vec = [0.0] * dim
    if len(blob) < n:
        blob = (blob + " " * n)[:n]
    for i in range(len(blob) - n + 1):
        gram = blob[i : i + n]
        digest = hashlib.md5(gram.encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "little") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vec[idx] += sign
    return _l2_normalize(vec)


def _l2_normalize(vec: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    return float(sum(x * y for x, y in zip(a, b)))


def token_overlap(query: str, doc: str) -> float:
    """Jaccard on alphanumeric tokens — cheap lexical complement."""
    q = set(normalize_text(query).split())
    d = set(normalize_text(doc).split())
    if not q or not d:
        return 0.0
    return len(q & d) / len(q | d)


def hybrid_score(query: str, doc: str, query_vec: Sequence[float], doc_vec: Sequence[float]) -> float:
    """0.65 hashed-cosine + 0.35 lexical overlap."""
    return 0.65 * cosine(query_vec, doc_vec) + 0.35 * token_overlap(query, doc)


_DENSE_CACHE: Dict[str, List[float]] = {}
_DENSE_DOWN = False


def _embed_endpoint(base_url: Optional[str]) -> str:
    if not base_url:
        try:
            import llm_config

            base_url = llm_config.LLM_BASE_URL
        except Exception:
            base_url = os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    return base_url.rstrip("/") + "/api/embeddings"


def dense_vectors(
    texts: Iterable[str],
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 4.0,
) -> List[Optional[List[float]]]:
    """Dense vectors aligned with ``texts``. A failed item is None; the rest stay.

    Successful vectors are cached for the process. If the embed server is down,
    later calls in this process stay on hashed n-grams.
    """
    global _DENSE_DOWN
    items = list(texts)
    model = model or os.environ.get("AGENTIC_EMBED_MODEL") or ""
    if not model or _DENSE_DOWN:
        return [None] * len(items)
    try:
        import requests
    except Exception:
        return [None] * len(items)
    url = _embed_endpoint(base_url)
    out: List[Optional[List[float]]] = []
    for text in items:
        key = f"{model}\n{normalize_text(text)[:2000]}"
        cached = _DENSE_CACHE.get(key)
        if cached is not None:
            out.append(cached)
            continue
        try:
            resp = requests.post(
                url,
                json={"model": model, "prompt": text},
                timeout=timeout,
            )
        except Exception as exc:
            logger.debug("Ollama embed unavailable: %s", exc)
            _DENSE_DOWN = True
            out.extend([None] * (len(items) - len(out)))
            return out
        if resp.status_code != 200:
            logger.debug("Ollama embed HTTP %s; hashed n-grams only", resp.status_code)
            _DENSE_DOWN = True
            out.extend([None] * (len(items) - len(out)))
            return out
        try:
            payload = resp.json()
        except Exception:
            out.append(None)
            continue
        vec = payload.get("embedding") or (payload.get("data") or [{}])[0].get("embedding")
        if not vec:
            out.append(None)
            continue
        normed = _l2_normalize([float(v) for v in vec])
        _DENSE_CACHE[key] = normed
        out.append(normed)
    return out


def blend_with_dense(
    lexical: float,
    query_dense: Optional[Sequence[float]],
    doc_dense: Optional[Sequence[float]],
) -> float:
    """Blend a hashed/lexical score with dense cosine when both vectors exist."""
    if query_dense is None or doc_dense is None:
        return lexical
    return 0.55 * lexical + 0.45 * cosine(query_dense, doc_dense)


def ollama_embed(
    texts: Iterable[str],
    *,
    base_url: Optional[str] = None,
    model: Optional[str] = None,
    timeout: float = 4.0,
) -> Optional[List[List[float]]]:
    """Best-effort dense embeddings from Ollama. Returns None if any item fails."""
    vectors = dense_vectors(
        texts, base_url=base_url, model=model, timeout=timeout
    )
    if not vectors or any(v is None for v in vectors):
        return None
    return [v for v in vectors if v is not None]
