"""Versioned campaign / per-sim JSON snapshots (JSONL stays the append-only log)."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from agentic.campaign.spec import CampaignSpec, spec_from_state

logger = logging.getLogger(__name__)

SNAPSHOT_SCHEMA_VERSION = "1.0"


def spec_hash(spec: Any) -> str:
    """Stable short hash of a CampaignSpec (or its dict)."""
    if spec is None:
        return ""
    if isinstance(spec, CampaignSpec):
        data = spec.to_dict()
    elif isinstance(spec, dict):
        data = spec
    else:
        data = {"repr": str(spec)}
    blob = json.dumps(data, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def campaign_state_path(base_dir: str | Path) -> Path:
    return Path(base_dir).resolve() / "campaign" / "state.json"


def per_sim_state_path(sim_dir: str | Path) -> Path:
    return Path(sim_dir).resolve() / "state.json"


def write_campaign_state_snapshot(state: Dict[str, Any]) -> Optional[Path]:
    """Write ``{base}/campaign/state.json`` (schema, spec hash, contract)."""
    base = _campaign_base(state)
    if not base:
        return None
    spec = spec_from_state(state)
    spec_dict = spec.to_dict() if spec else (state.get("campaign_spec") or {})
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "timestamp": datetime.now().isoformat(),
        "workflow_status": state.get("workflow_status"),
        "spec_hash": spec_hash(spec or spec_dict),
        "mode": spec.mode if spec else state.get("campaign_mode"),
        "family_modular": bool(spec.family_modular) if spec else False,
        "n_systems": spec.n_systems if spec else len(state.get("sim_prompts") or []),
        "labels": list(spec.labels) if spec else [
            (p.get("label") if isinstance(p, dict) else "")
            for p in (state.get("sim_prompts") or [])
        ],
        "completed_pipeline_stages": list(state.get("completed_pipeline_stages") or []),
        "science_contract": spec.contract.to_dict() if spec else {},
        "required_feature_columns": (
            list(spec.analysis_recipe.required_feature_columns) if spec else []
        ),
        "required_calculations": list(spec.pin_tools) if spec else [],
        "pin_tools": list(spec.pin_tools) if spec else [],
        "campaign_spec": spec_dict,
        "multi_sim_base_dir": str(base),
    }
    path = campaign_state_path(base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def write_per_sim_state_snapshot(
    state: Dict[str, Any],
    sim_dir: Optional[str | Path] = None,
) -> Optional[Path]:
    """Write ``{label}/state.json`` with stages, reps, and science contract."""
    root = Path(str(sim_dir or state.get("working_directory") or "")).resolve()
    if not str(root) or root == Path("."):
        return None
    if not root.exists():
        root.mkdir(parents=True, exist_ok=True)

    spec = spec_from_state(state)
    science: Dict[str, Any] = {}
    try:
        from agentic.campaign.contracts import per_sim_science_complete

        science = per_sim_science_complete(str(root), spec=spec, state=state)
    except Exception as exc:
        science = {"ok": False, "reason": str(exc)}

    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "timestamp": datetime.now().isoformat(),
        "label": root.name,
        "working_directory": str(root),
        "workflow_status": state.get("workflow_status"),
        "spec_hash": spec_hash(spec),
        "completed_pipeline_stages": list(state.get("completed_pipeline_stages") or []),
        "hpc_reps": _hpc_rep_records(root),
        "science": science,
        "user_goal": (state.get("user_goal_original") or state.get("user_goal") or "")[:500],
    }
    path = per_sim_state_path(root)
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def persist_state_snapshots(state: Dict[str, Any]) -> None:
    """Write campaign + active per-sim snapshots. Failures are logged, not raised."""
    try:
        write_campaign_state_snapshot(state)
    except Exception as exc:
        logger.warning("campaign state.json snapshot failed: %s", exc)
    try:
        base = _campaign_base(state)
        active = state.get("working_directory")
        if active:
            active_path = Path(str(active)).resolve()
            if not base or active_path != Path(str(base)).resolve():
                write_per_sim_state_snapshot(state, active_path)
            elif not state.get("is_multi_simulation"):
                write_per_sim_state_snapshot(state, active_path)
    except Exception as exc:
        logger.warning("per-sim state.json snapshot failed: %s", exc)


def load_campaign_state_snapshot(base_dir: str | Path) -> Optional[Dict[str, Any]]:
    path = campaign_state_path(base_dir)
    return _read_json(path)


def load_per_sim_state_snapshot(sim_dir: str | Path) -> Optional[Dict[str, Any]]:
    path = per_sim_state_path(sim_dir)
    return _read_json(path)


def merge_snapshot_into_state(state: Dict[str, Any], base_dir: str | Path) -> Dict[str, Any]:
    """Fill missing spec / stage fields from the JSON snapshot (JSONL wins when set)."""
    snap = load_campaign_state_snapshot(base_dir)
    if not snap:
        return state
    if not state.get("campaign_spec") and snap.get("campaign_spec"):
        state["campaign_spec"] = snap["campaign_spec"]
    if not state.get("completed_pipeline_stages") and snap.get("completed_pipeline_stages"):
        state["completed_pipeline_stages"] = list(snap["completed_pipeline_stages"])
    return state


def _campaign_base(state: Dict[str, Any]) -> Optional[Path]:
    raw = state.get("multi_sim_base_dir") or state.get("working_directory")
    if not raw:
        return None
    return Path(str(raw)).resolve()


def _hpc_rep_records(sim_dir: Path) -> List[Dict[str, Any]]:
    try:
        from src.analysis.replicate_paths import (
            discover_hpc_rep_dirs,
            resolve_production_topology,
            resolve_production_trajectory,
        )
    except Exception:
        return []
    rows: List[Dict[str, Any]] = []
    try:
        for hpc in discover_hpc_rep_dirs(str(sim_dir)):
            topo = resolve_production_topology(hpc)
            traj = resolve_production_trajectory(hpc)
            rows.append(
                {
                    "rep_id": hpc.name if hpc.name.startswith("rep") else "hpc",
                    "hpc_dir": str(hpc.resolve()),
                    "topology": str(topo.resolve()) if topo else "",
                    "trajectory": str(traj.resolve()) if traj else "",
                }
            )
    except Exception as exc:
        logger.debug("hpc_rep_records: %s", exc)
    return rows


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None
    return data if isinstance(data, dict) else None
