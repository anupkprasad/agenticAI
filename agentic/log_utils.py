"""Log utilities for agentic scripts.

Contains a small helper to reconstruct a human-friendly assistant
paragraph from the LLM's NDJSON/streamed output.
"""
from __future__ import annotations

import json
import re
from typing import Optional


def reconstruct_assistant_text(raw_text: Optional[str]) -> str:
    """Turn streamed/NDJSON raw_text into a readable assistant paragraph.

    Returns a multi-line string (one sentence per line) suitable for
    writing into logs for humans to read. The function is conservative and
    avoids inserting tokenized/broken JSON payloads or LLM metadata.
    """
    if not raw_text:
        return ""
    pieces = []
    thinking_fragments = []

    for ln in str(raw_text).splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            obj = json.loads(ln)
        except Exception:
            # Not JSON: append as-is
            pieces.append(ln)
            continue

        if isinstance(obj, dict):
            msg = obj.get('message') if isinstance(obj.get('message'), dict) else None
            if msg:
                content = msg.get('content')
                thinking = msg.get('thinking')
                if content:
                    # If content is itself JSON, skip it here (we keep
                    # parsed INVOKE_RESULT elsewhere). Otherwise append
                    # non-JSON content after flushing thinking fragments.
                    try:
                        json.loads(content)
                        is_json_content = True
                    except Exception:
                        is_json_content = False

                    if not is_json_content:
                        toks = str(content).split()
                        avg_len = sum(len(t) for t in toks) / max(1, len(toks))
                        if not (len(toks) > 6 and avg_len < 2.5):
                            if thinking_fragments:
                                pieces.append("".join(thinking_fragments))
                                thinking_fragments = []
                            pieces.append(str(content))
                    continue
                if thinking:
                    thinking_fragments.append(str(thinking))
                    continue

            # prefer common top-level fields
            for k in ('response', 'content', 'text'):
                if k in obj and obj.get(k):
                    if thinking_fragments:
                        pieces.append("".join(thinking_fragments))
                        thinking_fragments = []
                    pieces.append(str(obj.get(k)))
                    break
            else:
                thinking = obj.get('thinking') or obj.get('delta')
                if thinking:
                    thinking_fragments.append(str(thinking))
                else:
                    # ignore streaming metadata objects (model/message/done)
                    if isinstance(obj, dict) and 'model' in obj and 'message' in obj:
                        continue
                    pieces.append(str(obj))
        else:
            pieces.append(str(obj))

    if thinking_fragments:
        pieces.append("".join(thinking_fragments))

    joined = " ".join(pieces)
    joined = re.sub(r"\s+", " ", joined).strip()

    # split into sentences for multiline readability
    sentences = re.split(r'(?<=[.!?])\s+', joined)
    lines = [s.strip() for s in sentences if s.strip()]
    return "\n".join(lines)
