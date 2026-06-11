"""Helpers for resolving and deduplicating PDB path lists."""
from pathlib import Path
from typing import List


def unique_pdb_paths(paths: List[str]) -> List[str]:
    """Return unique PDB paths, preserving first-seen order.

    Goals often mention the same ``.pdb`` filename multiple times; without
    deduplication the multi-simulation loop runs duplicate jobs.
    """
    seen: set[str] = set()
    unique: List[str] = []
    for raw in paths:
        if not raw:
            continue
        p = Path(raw)
        if p.exists():
            key = str(p.resolve())
        else:
            key = str(p).replace("\\", "/").lower()
        if key not in seen:
            seen.add(key)
            unique.append(raw)
    return unique
