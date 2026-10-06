"""
Deterministic SLURM submit parameters shared by pool mode and the HPC agent.

Pool orchestration stays in ``multi_sim_hpc_pool``; this module centralizes
production length, walltime, and SLURM resource defaults (no LLM).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_hpc_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    path = Path(config_path) if config_path else _DEFAULT_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except OSError as exc:
        logger.warning("Failed to load HPC config from %s: %s", path, exc)
        return {}


def estimate_system_size(coordinates_file: Optional[str]) -> int:
    """Estimate atom count from a GRO file (second line)."""
    if not coordinates_file or not Path(coordinates_file).is_file():
        return 50000
    try:
        with open(coordinates_file, "r", encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
        if len(lines) > 1:
            return int(lines[1].strip())
    except (OSError, ValueError):
        pass
    return 50000


def _goal_text(workflow_state: Optional[Dict[str, Any]]) -> str:
    state = workflow_state or {}
    parts = [
        state.get("user_goal"),
        state.get("user_goal_original"),
        state.get("master_enriched_prompt"),
        state.get("enriched_prompt"),
    ]
    return "\n".join(p for p in parts if p)


def _sim_prompt_entry(
    workflow_state: Optional[Dict[str, Any]], sim_label: str
) -> Dict[str, Any]:
    for sp in (workflow_state or {}).get("sim_prompts") or []:
        if sp.get("label") == sim_label:
            return sp
    return {}


def resolve_production_ns(
    workflow_state: Optional[Dict[str, Any]],
    sim_label: str,
    sim_working_dir: str,
) -> float:
    """Production length (ns) from per-sim goal text, global state, or config default."""
    from src.simsetup.system_options import production_ns_for_sim

    state = workflow_state or {}
    sp = _sim_prompt_entry(state, sim_label)
    goal = _goal_text(state)
    pdb = sp.get("pdb") or sp.get("source_pdb")
    if not pdb:
        for name in ("cleaned_pdb", "raw_pdb", "coordinates"):
            val = state.get(name)
            if val and sim_label.lower() in str(val).lower():
                pdb = val
                break

    per_sim = production_ns_for_sim(goal, pdb_path=pdb, label=sim_label)
    if per_sim is not None:
        return float(per_sim)
    if state.get("production_ns") is not None:
        return float(state["production_ns"])

    config = load_hpc_config()
    default_ns = config.get("time_estimation", {}).get("default_production_ns", 10.0)
    return float(default_ns)


def _coordinates_path(sim_working_dir: str) -> Optional[str]:
    wd = Path(sim_working_dir)
    for candidate in (
        wd / "simsetup" / "system.gro",
        wd / "hpc" / "system.gro",
    ):
        if candidate.is_file():
            return str(candidate)
    gro_files = sorted((wd / "simsetup").glob("*.gro"))
    if gro_files:
        return str(gro_files[0])
    return None


def simulation_phases(
    simsetup_dir: str,
    hpc_dir: str,
    workflow_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """MD phases for the SLURM script (includes minim2 when present)."""
    state = workflow_state or {}
    simsetup = Path(simsetup_dir)
    hpc = Path(hpc_dir)
    phases = ["minim", "nvt", "npt", "md"]
    if state.get("extended_minimization"):
        phases = ["minim", "minim2", "nvt", "npt", "md"]
    elif (simsetup / "minim2.mdp").is_file() or (hpc / "minim2.mdp").is_file():
        phases = ["minim", "minim2", "nvt", "npt", "md"]
    return phases


def derive_job_name(sim_label: str, sim_working_dir: str) -> str:
    """Unique SLURM job name from sim label / working directory."""
    if sim_label:
        safe = re.sub(r"[^A-Za-z0-9_\-]", "_", sim_label)[:40]
        if safe:
            return safe
    stem = Path(sim_working_dir).name
    safe = re.sub(r"[^A-Za-z0-9_\-]", "_", stem)[:40]
    return safe or "md_simulation"


def user_requested_walltime(workflow_state: Optional[Dict[str, Any]] = None) -> bool:
    """True when the user goal or state explicitly sets SLURM walltime."""
    from src.hpc.time_options import _combined_goal_text, parse_walltime_from_text

    state = workflow_state or {}
    if state.get("hpc_time_limit"):
        return True
    return parse_walltime_from_text(_combined_goal_text(state)) is not None


def build_slurm_script_params(
    *,
    job_name: str,
    hpc_dir: str,
    simsetup_dir: str,
    workflow_state: Optional[Dict[str, Any]] = None,
    estimate_slurm_time: Optional[str] = None,
) -> Dict[str, Any]:
    """SLURM script kwargs aligned with ``MDHPCAgent._enrich_tool_params`` (deterministic).

    Walltime uses config/default (typically 5 days) unless the user explicitly
    requested a limit in the goal or ``state['hpc_time_limit']``. Automatic
    production-length estimates are not applied in pool mode.
    """
    from src.hpc.time_options import resolve_hpc_time_limit

    config = load_hpc_config()
    defaults = config.get("slurm_defaults", {})
    use_estimate = estimate_slurm_time if user_requested_walltime(workflow_state) else None
    params: Dict[str, Any] = {
        "job_name": job_name,
        "working_dir": hpc_dir,
        "simulation_phases": simulation_phases(simsetup_dir, hpc_dir, workflow_state),
        "time_limit": resolve_hpc_time_limit(
            state=workflow_state,
            estimate_slurm_time=use_estimate,
        ),
    }
    for key in (
        "partition",
        "cpus_per_task",
        "memory",
        "gpu_count",
        "gromacs_module",
        "topology_file",
        "input_structure",
        "exclude_nodes",
    ):
        if key in defaults and defaults[key] not in (None, ""):
            params[key] = defaults[key]
    state = workflow_state or {}
    # Per-run override (CLI/env/campaign) wins over config.yaml.
    if state.get("hpc_exclude_nodes"):
        params["exclude_nodes"] = state["hpc_exclude_nodes"]
    if state.get("user_email"):
        params["email"] = state["user_email"]
    return params


def estimate_walltime_for_sim(
    production_ns: float,
    sim_working_dir: str,
) -> Dict[str, Any]:
    """Run ``estimate_simulation_time`` with resolved ns and system size."""
    from src.hpc.time_estimator import estimate_simulation_time

    coords = _coordinates_path(sim_working_dir)
    system_size = estimate_system_size(coords)
    return estimate_simulation_time.func(
        production_ns=production_ns,
        system_size=system_size,
    )
