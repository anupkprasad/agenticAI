"""Per-replicate analysis inventory — absolute traj/topo and shared maps."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

INVENTORY_SCHEMA_VERSION = "1.0"
INVENTORY_NAME = "inventory.json"

STAGE_FOLDER = {
    "preprocessing": "preprocess",
    "preprocess": "preprocess",
    "simsetup": "simsetup",
    "setup": "simsetup",
    "hpc": "hpc",
    "analysis": "analysis",
    "reporter": "reporter",
    "pre_combined": "cross_sim",
    "post_combined": "analysis",
}


def inventory_path(analysis_dir: str | Path) -> Path:
    return Path(analysis_dir) / INVENTORY_NAME


def write_rep_inventory(
    *,
    analysis_dir: str | Path,
    hpc_dir: str | Path = "",
    sim_root: str | Path = "",
    label: str = "",
    topology: str = "",
    trajectory: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write ``analysis/repXX/inventory.json`` (or flat ``analysis/inventory.json``)."""
    adir = Path(analysis_dir)
    adir.mkdir(parents=True, exist_ok=True)
    root = Path(sim_root) if sim_root else _infer_sim_root(adir)
    hpc = Path(hpc_dir) if hpc_dir else Path()

    topo = _abs_file(topology) or _resolve_topo(hpc)
    traj = _abs_file(trajectory) or _resolve_traj(hpc)
    pocket = discover_mapped_path(root, ("pocket_mapped.json", "pocket_map.json"))
    global_mapped = discover_mapped_path(
        root,
        (
            "global_consensus_msa.json",
            "global_mapped.json",
            "reference_msa_alignment.json",
        ),
    )

    payload: Dict[str, Any] = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "timestamp": datetime.now().isoformat(),
        "label": label or (root.name if root else ""),
        "rep_id": adir.name if str(adir.name).startswith("rep") else "flat",
        "sim_root": str(root.resolve()) if root else "",
        "analysis_dir": str(adir.resolve()),
        "hpc_dir": str(hpc.resolve()) if hpc_dir and hpc.exists() else str(hpc_dir or ""),
        "topology": topo,
        "trajectory": traj,
        "pocket_mapped": pocket,
        "global_mapped": global_mapped,
        "outputs": dict((extra or {}).get("outputs") or extra or {}),
    }
    path = inventory_path(adir)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    logger.info("Wrote analysis inventory %s traj=%s", path, traj)
    return path


def load_rep_inventory(analysis_dir: str | Path) -> Optional[Dict[str, Any]]:
    path = inventory_path(analysis_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_stage_inventory(stage_dir: str | Path) -> Optional[Dict[str, Any]]:
    """Load ``{stage}/inventory.json`` (preprocess, simsetup, hpc, analysis, …)."""
    return load_rep_inventory(stage_dir)


def write_stage_inventory(
    *,
    stage_dir: str | Path,
    stage: str = "",
    sim_root: str | Path = "",
    label: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> Path:
    """Write ``{stage}/inventory.json`` with absolute paths to key artifacts."""
    sdir = Path(stage_dir)
    sdir.mkdir(parents=True, exist_ok=True)
    stage_name = stage or sdir.name
    root = Path(sim_root) if sim_root else _infer_sim_root_for_stage(sdir)
    files = _list_stage_files(sdir)
    pocket = discover_mapped_path(
        root, ("pocket_mapped.json", "pocket_map.json")
    )
    global_mapped = discover_mapped_path(
        root,
        (
            "global_consensus_msa.json",
            "global_mapped.json",
            "reference_msa_alignment.json",
        ),
    )
    payload: Dict[str, Any] = {
        "schema_version": INVENTORY_SCHEMA_VERSION,
        "timestamp": datetime.now().isoformat(),
        "stage": stage_name,
        "label": label or (root.name if root else ""),
        "sim_root": str(root.resolve()) if root and root.exists() else str(root or ""),
        "stage_dir": str(sdir.resolve()),
        "pocket_mapped": pocket,
        "global_mapped": global_mapped,
        "files": files,
    }
    if extra:
        for key, val in extra.items():
            if key == "outputs":
                payload["outputs"] = val
                continue
            if val in (None, ""):
                continue
            payload[key] = val
    path = inventory_path(sdir)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    logger.info("Wrote stage inventory %s stage=%s", path, stage_name)
    return path


def discover_mapped_path(sim_root: Path | str, names: tuple[str, ...]) -> str:
    """Find a shared map via inventories first, then the parent-folder walk."""
    from_inv = _from_inventories(sim_root, names)
    if from_inv:
        return from_inv
    return _discover_shared(Path(sim_root) if sim_root else Path(), names)


def _from_inventories(sim_root: Path | str, names: tuple[str, ...]) -> str:
    if not sim_root:
        return ""
    root = Path(sim_root)
    candidates = [
        root / "cross_sim" / INVENTORY_NAME,
        root / "analysis" / INVENTORY_NAME,
        root.parent / "cross_sim" / INVENTORY_NAME,
        root.parent / "analysis" / INVENTORY_NAME,
    ]
    analysis = root / "analysis"
    if analysis.is_dir():
        for child in sorted(analysis.iterdir()):
            if child.name.startswith("rep"):
                candidates.append(child / INVENTORY_NAME)
    keys = []
    for name in names:
        if "pocket" in name:
            keys.append("pocket_mapped")
        if "global" in name or "msa" in name or "alignment" in name:
            keys.append("global_mapped")
    for cand in candidates:
        if not cand.is_file():
            continue
        try:
            data = json.loads(cand.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        for key in keys:
            val = data.get(key)
            if val and Path(str(val)).is_file():
                return str(Path(val).resolve())
        files = data.get("files") or {}
        if isinstance(files, dict):
            for name in names:
                val = files.get(name)
                if val and Path(str(val)).is_file():
                    return str(Path(val).resolve())
    return ""


def _infer_sim_root_for_stage(stage_dir: Path) -> Path:
    if stage_dir.name.startswith("rep"):
        return stage_dir.parent.parent
    if stage_dir.name in {
        "preprocess",
        "simsetup",
        "hpc",
        "analysis",
        "reporter",
        "cross_sim",
    }:
        return stage_dir.parent
    return stage_dir.parent


def _list_stage_files(stage_dir: Path, limit: int = 40) -> Dict[str, str]:
    files: Dict[str, str] = {}
    if not stage_dir.is_dir():
        return files
    for item in sorted(stage_dir.iterdir()):
        if item.name == INVENTORY_NAME:
            continue
        if item.is_file():
            files[item.name] = str(item.resolve())
        if len(files) >= limit:
            break
    return files


def _infer_sim_root(analysis_dir: Path) -> Path:
    # analysis/repXX → sim; analysis/ → sim
    if analysis_dir.name.startswith("rep"):
        return analysis_dir.parent.parent
    if analysis_dir.name == "analysis":
        return analysis_dir.parent
    return analysis_dir.parent


def _discover_shared(sim_root: Path, names: tuple[str, ...]) -> str:
    """Find shared maps under this study or its parent campaign folder.

    Works for both per-protein roots (``run/p17612_ATP``) and the campaign
    base (``run/``), so combined reporter inventories resolve ``cross_sim/``.
    """
    if not sim_root:
        return ""
    root = Path(sim_root)
    folders = [
        root / "cross_sim",
        root / "analysis",
        root.parent / "cross_sim",
        root.parent / "analysis",
    ]
    for folder in folders:
        for name in names:
            cand = folder / name
            if cand.is_file():
                return str(cand.resolve())
    return ""


def _resolve_topo(hpc: Path) -> str:
    if not hpc or not hpc.exists():
        return ""
    try:
        from src.analysis.replicate_paths import resolve_production_topology

        found = resolve_production_topology(hpc)
        return str(found.resolve()) if found else ""
    except Exception:
        return ""


def _resolve_traj(hpc: Path) -> str:
    if not hpc or not hpc.exists():
        return ""
    try:
        from src.analysis.replicate_paths import resolve_production_trajectory

        found = resolve_production_trajectory(hpc)
        return str(found.resolve()) if found else ""
    except Exception:
        return ""


def write_stage_inventory_for_state(state: Optional[Dict[str, Any]], stage: str) -> Optional[Path]:
    """Write ``{sim}/{stage}/inventory.json`` after a workflow node succeeds."""
    if not state:
        return None
    sim = state.get("working_directory")
    if not sim:
        return None
    folder = STAGE_FOLDER.get(str(stage).strip().lower(), str(stage).strip().lower())
    extra: Dict[str, Any] = {}
    if folder == "hpc":
        extra["topology"] = str(state.get("tpr_file") or "")
        extra["trajectory"] = str(state.get("trajectory_path") or "")
        extra["hpc_dir"] = str(state.get("hpc_dir") or "")
    if folder == "preprocess":
        extra["cleaned_pdb"] = str(state.get("cleaned_pdb") or "")
    if folder == "simsetup":
        extra["topology"] = str(state.get("topology") or "")
        extra["coordinates"] = str(state.get("coordinates") or "")
    if folder == "analysis":
        extra["topology"] = str(state.get("tpr_file") or "")
        extra["trajectory"] = str(state.get("trajectory_path") or "")
    try:
        return write_stage_inventory(
            stage_dir=Path(sim) / folder,
            stage=folder,
            sim_root=sim,
            label=str(state.get("current_sim_label") or Path(sim).name),
            extra=extra,
        )
    except Exception as exc:
        logger.warning("stage inventory write failed for %s: %s", stage, exc)
        return None


def _abs_file(path: str) -> str:
    if not path:
        return ""
    p = Path(path)
    if p.is_file():
        return str(p.resolve())
    return ""
