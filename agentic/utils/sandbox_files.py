"""List/grep/inventory tools restricted to the study directory (campaign or sim root)."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

SANDBOX_TOOL_NAMES = frozenset({"list_dir", "grep_file", "read_inventory"})

_TEXT_EXTS = {
    ".pdb", ".gro", ".top", ".itp", ".mdp", ".log", ".txt",
    ".xvg", ".json", ".jsonl", ".csv", ".sh", ".slurm",
    ".out", ".py", ".yaml", ".yml", ".md",
}


def sandbox_roots_from_state(state: Optional[Dict[str, Any]] = None) -> List[Path]:
    """Allowed roots: campaign base and the bound simulation directory."""
    state = state or {}
    roots: List[Path] = []
    for key in (
        "multi_sim_base_dir",
        "working_directory",
        "hitl_view_working_directory",
    ):
        raw = state.get(key)
        if raw:
            p = Path(str(raw)).expanduser()
            if p.exists():
                roots.append(p.resolve())
    # Unique, keep order
    seen = set()
    out: List[Path] = []
    for r in roots:
        if r not in seen:
            seen.add(r)
            out.append(r)
    return out


def resolve_sandbox_path(
    path_str: str,
    roots: Sequence[Path | str],
    *,
    must_exist: bool = False,
) -> Optional[Path]:
    """Resolve *path_str* under one of *roots*. None if it would escape."""
    if not roots:
        return None
    raw = Path(path_str or ".")
    resolved_roots = [Path(r).resolve() for r in roots]
    candidates: List[Path] = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        for root in resolved_roots:
            candidates.append(root / raw)
    for cand in candidates:
        try:
            resolved = cand.resolve()
        except OSError:
            continue
        if not any(_is_relative_to(resolved, root) for root in resolved_roots):
            continue
        if must_exist and not resolved.exists():
            continue
        return resolved
    return None


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def list_dir_sandboxed(
    directory_path: str = ".",
    *,
    roots: Sequence[Path | str],
) -> Dict[str, Any]:
    target = resolve_sandbox_path(directory_path or ".", roots)
    if target is None:
        return {
            "success": False,
            "error": f"access denied or not found: {directory_path}",
        }
    if not target.is_dir():
        return {"success": False, "error": f"not a directory: {directory_path}"}
    entries = []
    for item in sorted(target.iterdir()):
        entries.append(
            {
                "name": item.name,
                "type": "dir" if item.is_dir() else "file",
                "bytes": item.stat().st_size if item.is_file() else None,
            }
        )
    return {
        "success": True,
        "path": str(target),
        "entries": entries,
        "listing": "\n".join(
            f"  {e['name']}/" if e["type"] == "dir" else f"  {e['name']}  ({e['bytes']} bytes)"
            for e in entries
        )
        or "(empty directory)",
    }


def grep_sandboxed(
    pattern: str,
    filepath: str = ".",
    *,
    roots: Sequence[Path | str],
    max_matches: int = 40,
) -> Dict[str, Any]:
    try:
        rx = re.compile(pattern)
    except re.error as exc:
        return {"success": False, "error": f"invalid regex: {exc}"}
    root0 = Path(roots[0]).resolve() if roots else Path(".")
    matches: List[str] = []

    def _search(path: Path) -> None:
        nonlocal matches
        try:
            for i, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if rx.search(line):
                    try:
                        rel = path.relative_to(root0)
                    except ValueError:
                        rel = path
                    matches.append(f"{rel}:{i}: {line.rstrip()}")
                    if len(matches) >= max_matches:
                        return
        except OSError:
            return

    if filepath in (".", "", "*"):
        for root in roots:
            base = Path(root)
            for f in sorted(base.rglob("*")):
                if f.is_file() and f.suffix.lower() in _TEXT_EXTS:
                    _search(f)
                    if len(matches) >= max_matches:
                        break
            if len(matches) >= max_matches:
                break
    else:
        target = resolve_sandbox_path(filepath, roots, must_exist=True)
        if target is None:
            return {"success": False, "error": f"file not found: {filepath}"}
        if target.is_dir():
            for f in sorted(target.rglob("*")):
                if f.is_file() and f.suffix.lower() in _TEXT_EXTS:
                    _search(f)
                    if len(matches) >= max_matches:
                        break
        else:
            _search(target)

    return {
        "success": True,
        "n_matches": len(matches),
        "matches": matches,
        "message": "\n".join(matches) if matches else f"(no matches for '{pattern}')",
    }


def read_inventory_sandboxed(
    stage: str = "",
    *,
    roots: Sequence[Path | str],
    sim_root: str = "",
) -> Dict[str, Any]:
    """Read ``{stage}/inventory.json`` (or analysis/repXX) under the sandbox."""
    from src.analysis.inventory import (
        INVENTORY_NAME,
        load_rep_inventory,
        load_stage_inventory,
    )

    searched: List[str] = []
    stage = (stage or "").strip().strip("/")
    candidates: List[Path] = []
    bases = [Path(sim_root)] if sim_root else [Path(r) for r in roots]
    for base in bases:
        if stage:
            candidates.append(base / stage / INVENTORY_NAME)
            if stage == "analysis":
                candidates.append(base / "analysis" / INVENTORY_NAME)
        else:
            for name in (
                "preprocess",
                "simsetup",
                "hpc",
                "analysis",
                "reporter",
                "cross_sim",
            ):
                candidates.append(base / name / INVENTORY_NAME)
            # Newest analysis/repXX inventory
            analysis = base / "analysis"
            if analysis.is_dir():
                for child in sorted(analysis.iterdir()):
                    if child.name.startswith("rep") and (child / INVENTORY_NAME).is_file():
                        candidates.append(child / INVENTORY_NAME)

    found: List[Dict[str, Any]] = []
    for cand in candidates:
        searched.append(str(cand))
        if not cand.is_file():
            continue
        if cand.parent.name.startswith("rep"):
            data = load_rep_inventory(cand.parent)
        else:
            data = load_stage_inventory(cand.parent)
        if data:
            found.append(data)
    if not found:
        return {
            "success": False,
            "error": "inventory.json not found",
            "searched": searched[:12],
        }
    return {
        "success": True,
        "n": len(found),
        "inventories": found,
        "message": json.dumps(found[0], indent=2, default=str),
    }


def execute_sandbox_tool(
    tool_name: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    roots: Sequence[Path | str],
    sim_root: str = "",
) -> Optional[Dict[str, Any]]:
    """Run a sandbox file tool. Returns None if *tool_name* is not one of them."""
    name = (tool_name or "").strip()
    if name not in SANDBOX_TOOL_NAMES:
        return None
    params = params or {}
    if name == "list_dir":
        path = params.get("directory_path") or params.get("path") or params.get("dir") or "."
        return list_dir_sandboxed(str(path), roots=roots)
    if name == "grep_file":
        return grep_sandboxed(
            str(params.get("regex_pattern") or params.get("pattern") or ""),
            str(params.get("filepath") or params.get("path") or "."),
            roots=roots,
        )
    return read_inventory_sandboxed(
        str(params.get("stage") or params.get("path") or ""),
        roots=roots,
        sim_root=sim_root or str(params.get("sim_root") or ""),
    )


def sandbox_tool_records() -> List[Dict[str, Any]]:
    """Planner-facing metadata injected for every field agent."""
    return [
        {
            "name": "list_dir",
            "description": (
                "List files under the campaign or simulation root. "
                "Sandboxed — cannot leave the campaign tree."
            ),
            "parameters": {
                "directory_path": {
                    "type": "string",
                    "required": False,
                    "description": "Relative path (default '.')",
                }
            },
        },
        {
            "name": "grep_file",
            "description": (
                "Regex search in one file or the sandbox tree. "
                "Use to find pocket_mapped.json, MDP settings, or log errors."
            ),
            "parameters": {
                "regex_pattern": {"type": "string", "required": True},
                "filepath": {
                    "type": "string",
                    "required": False,
                    "description": "File, directory, or '.' for all text files",
                },
            },
        },
        {
            "name": "read_inventory",
            "description": (
                "Read {stage}/inventory.json (absolute traj/topo, pocket_mapped, "
                "global_mapped). Prefer this over walking parent folders."
            ),
            "parameters": {
                "stage": {
                    "type": "string",
                    "required": False,
                    "description": "preprocess | simsetup | hpc | analysis | reporter",
                }
            },
        },
    ]
