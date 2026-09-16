"""Replicate path helpers for multi-replicate MD campaigns.

Layout when ``rep_num > 1``::

    {label}/
      preprocess/  simsetup/          # shared
      hpc/rep01/  hpc/rep02/ ...
      analysis/rep01/  analysis/rep02/ ...
      analysis/avg/

When ``rep_num == 1``, prefer legacy flat ``{label}/hpc/`` and ``{label}/analysis/``
(with optional discovery of ``rep01`` if already nested).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

_REP_DIR_RE = re.compile(r"^rep(\d+)$", re.IGNORECASE)


def normalize_rep_num(value: Any, default: int = 1) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return int(default)
    return max(1, n)


def format_rep_id(rep_index: int) -> str:
    """1-based index → ``rep01``."""
    if rep_index < 1:
        raise ValueError(f"rep_index must be ≥ 1, got {rep_index}")
    return f"rep{rep_index:02d}"


def parse_rep_id(name: str) -> Optional[int]:
    m = _REP_DIR_RE.match(str(name).strip())
    if not m:
        return None
    return int(m.group(1))


def iter_rep_ids(rep_num: int) -> List[str]:
    n = normalize_rep_num(rep_num)
    return [format_rep_id(i) for i in range(1, n + 1)]


def replicate_seed(base_seed: int, rep_index: int) -> int:
    """Deterministic production/NVT seed for replicate *rep_index* (1-based)."""
    return int(base_seed) + int(rep_index) - 1


def hpc_rep_dir(sim_dir: Path | str, rep_id: str, *, nested: bool) -> Path:
    root = Path(sim_dir) / "hpc"
    return root / rep_id if nested else root


def analysis_rep_dir(sim_dir: Path | str, rep_id: str, *, nested: bool) -> Path:
    root = Path(sim_dir) / "analysis"
    return root / rep_id if nested else root


def analysis_avg_dir(sim_dir: Path | str) -> Path:
    return Path(sim_dir) / "analysis" / "avg"


def uses_nested_reps(rep_num: int) -> bool:
    return normalize_rep_num(rep_num) > 1


def write_replicate_meta(
    hpc_dir: Path,
    *,
    rep_id: str,
    seed: int,
    parent_label: str,
    rep_index: int,
    rep_num: int,
) -> Path:
    hpc_dir.mkdir(parents=True, exist_ok=True)
    path = hpc_dir / "replicate.json"
    payload = {
        "rep_id": rep_id,
        "rep_index": int(rep_index),
        "rep_num": int(rep_num),
        "seed": int(seed),
        "parent_label": parent_label,
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def discover_hpc_rep_dirs(sim_dir: Path | str) -> List[Path]:
    """Return existing nested hpc/repXX dirs, else ``[hpc]`` if it looks populated."""
    hpc = Path(sim_dir) / "hpc"
    if not hpc.is_dir():
        return []
    nested = sorted(
        [p for p in hpc.iterdir() if p.is_dir() and parse_rep_id(p.name) is not None],
        key=lambda p: parse_rep_id(p.name) or 0,
    )
    if nested:
        return nested
    # Legacy flat
    return [hpc]


def discover_analysis_rep_dirs(sim_dir: Path | str) -> List[Path]:
    analysis = Path(sim_dir) / "analysis"
    if not analysis.is_dir():
        return []
    nested = sorted(
        [
            p
            for p in analysis.iterdir()
            if p.is_dir() and parse_rep_id(p.name) is not None
        ],
        key=lambda p: parse_rep_id(p.name) or 0,
    )
    if nested:
        return nested
    return [analysis]


def preferred_analysis_metric_dirs(sim_dir: Path | str) -> List[Path]:
    """Discovery order for combined collectors: avg → nested reps → flat analysis."""
    sim = Path(sim_dir)
    out: List[Path] = []
    avg = analysis_avg_dir(sim)
    if avg.is_dir():
        out.append(avg)
    reps = discover_analysis_rep_dirs(sim)
    # If only flat analysis (same as analysis/), keep once
    for d in reps:
        if d.resolve() != avg.resolve() and d not in out:
            out.append(d)
    return out


def resolve_production_trajectory(hpc_dir: Path) -> Optional[Path]:
    """Pick a production trajectory under an HPC (or hpc/repXX) directory."""
    names = (
        "mdWrap.xtc",
        "md.xtc",
        "prod.xtc",
        "production.xtc",
        "md_noPBC.xtc",
    )
    for name in names:
        p = hpc_dir / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def resolve_production_topology(hpc_dir: Path) -> Optional[Path]:
    """Pick a topology that matches the production trajectory atom count.

    Prefer ``md.tpr`` / ``md.gro`` from the same MD run. Fresh simsetup
    ``system.gro`` / ``solvated.gro`` staged under ``--reuse-hpc`` often have a
    different atom count than the reused ``mdWrap.xtc`` and must not win.
    """
    hpc = Path(hpc_dir)
    for name in ("md.tpr", "md.gro"):
        p = hpc / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    for name in ("npt.gro", "nvt.gro", "system.gro", "solvated.gro"):
        p = hpc / name
        if p.is_file() and p.stat().st_size > 0:
            return p
    return None


def pool_slot_key(label: str, rep_id: Optional[str] = None, *, nested: bool = True) -> str:
    """HPC pool / progress key. Nested multi-rep uses ``label::rep01``."""
    if nested and rep_id:
        return f"{label}::{rep_id}"
    return label


def split_pool_slot_key(key: str) -> Tuple[str, Optional[str]]:
    if "::" in key:
        label, rep = key.split("::", 1)
        return label, rep
    return key, None


def build_rep_plan(
    label: str,
    sim_dir: Path | str,
    rep_num: int,
    *,
    base_seed: int = 12345,
) -> List[Dict[str, Any]]:
    """Descriptor list for each replicate under a label."""
    nested = uses_nested_reps(rep_num)
    sim = Path(sim_dir)
    plan = []
    for i, rep_id in enumerate(iter_rep_ids(rep_num), start=1):
        seed = replicate_seed(base_seed, i)
        plan.append(
            {
                "label": label,
                "rep_id": rep_id,
                "rep_index": i,
                "rep_num": normalize_rep_num(rep_num),
                "seed": seed,
                "nested": nested,
                "hpc_dir": str(hpc_rep_dir(sim, rep_id, nested=nested)),
                "analysis_dir": str(analysis_rep_dir(sim, rep_id, nested=nested)),
                "slot_key": pool_slot_key(label, rep_id if nested else None, nested=nested),
            }
        )
    return plan


def discover_rep_num_on_disk(sim_dir: Path | str, fallback: int = 1) -> int:
    """Infer N from nested ``hpc/repXX`` (or analysis/repXX); else *fallback*."""
    nested = discover_hpc_rep_dirs(sim_dir)
    n_hpc = sum(1 for p in nested if parse_rep_id(p.name) is not None)
    if n_hpc >= 2:
        return n_hpc
    nested_a = discover_analysis_rep_dirs(sim_dir)
    n_an = sum(1 for p in nested_a if parse_rep_id(p.name) is not None)
    if n_an >= 2:
        return n_an
    return normalize_rep_num(fallback)


def effective_rep_num(state_or_rep: Any, sim_dir: Optional[Path | str] = None) -> int:
    """CLI/state rep_num, raised to match on-disk nested replicates when present."""
    if isinstance(state_or_rep, dict):
        declared = normalize_rep_num(state_or_rep.get("rep_num", 1))
        wd = sim_dir or state_or_rep.get("working_directory")
    else:
        declared = normalize_rep_num(state_or_rep)
        wd = sim_dir
    if wd:
        return max(declared, discover_rep_num_on_disk(wd, fallback=declared))
    return declared


def parse_rep_num_from_text(text: str, default: int = 1) -> int:
    """Soft-parse ``N replicates`` / ``N reps`` from goal text (CLI still wins)."""
    if not text:
        return normalize_rep_num(default)
    patterns = (
        r"\b(\d+)\s*replicates?\b",
        r"\b(\d+)\s*reps?\b",
        r"\brep(?:licate)?[_\s-]*num(?:ber)?\s*[:=]\s*(\d+)\b",
        r"\bwith\s+(\d+)\s+independent\s+(?:md\s+)?runs?\b",
    )
    for pat in patterns:
        m = re.search(pat, text, flags=re.IGNORECASE)
        if m:
            return normalize_rep_num(m.group(1), default=default)
    return normalize_rep_num(default)


def apply_gen_seed_to_mdp_dir(hpc_dir: Path | str, seed: int) -> List[str]:
    """Set ``gen_seed = <seed>`` in MDP files under *hpc_dir* (NVT velocity gen)."""
    root = Path(hpc_dir)
    if not root.is_dir():
        return []
    patched: List[str] = []
    seed_re = re.compile(r"(?im)^(\s*gen_seed\s*=\s*)(-?\d+)(\s*.*)$")
    for mdp in sorted(root.glob("*.mdp")):
        try:
            text = mdp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "gen_seed" not in text.lower():
            continue
        new_text, n = seed_re.subn(rf"\g<1>{int(seed)}\3", text)
        if n:
            mdp.write_text(new_text, encoding="utf-8")
            patched.append(str(mdp))
    return patched
