"""Simple StateGraph helper for workflow state and provenance.

This is a minimal, file-backed in-memory graph used by the Supervisor to
record workflow nodes (events) and edges. It's intentionally small — a later
implementation can replace this with a proper graph DB or persistence layer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
import json
from pathlib import Path
import time


@dataclass
class StateNode:
    id: str
    type: str
    payload: Dict[str, Any]
    ts: float = field(default_factory=time.time)


class StateGraph:
    """A tiny append-only state graph.

    Methods:
      - add_node(type, payload) -> node_id
      - add_edge(src_id, dst_id, label)
      - snapshot(path) -> writes JSON file
    """

    def __init__(self):
        self.nodes: Dict[str, StateNode] = {}
        self.edges: List[Dict[str, str]] = []

    def add_node(self, node_type: str, payload: Optional[Dict[str, Any]] = None) -> str:
        payload = payload or {}
        nid = f"n{len(self.nodes)+1}"
        node = StateNode(id=nid, type=node_type, payload=payload)
        self.nodes[nid] = node
        return nid

    def add_edge(self, src_id: str, dst_id: str, label: str = "next") -> None:
        self.edges.append({"src": src_id, "dst": dst_id, "label": label})

    def snapshot(self, path: str) -> None:
        out = {
            "nodes": {nid: {"type": n.type, "payload": n.payload, "ts": n.ts} for nid, n in self.nodes.items()},
            "edges": self.edges,
        }
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, indent=2))

    def get_node(self, node_id: str) -> Optional[StateNode]:
        return self.nodes.get(node_id)
