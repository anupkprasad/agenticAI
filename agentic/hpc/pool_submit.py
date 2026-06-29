"""
Submit-only HPC path for multi-sim pool (no blocking monitor loop).

Copies simsetup → hpc, creates SLURM script, sbatch — one job per simulation.
Uses deterministic SLURM defaults from config; walltime stays at the default
unless the user explicitly requests a limit in the goal.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from agentic.hpc.submit_params import (
    build_slurm_script_params,
    derive_job_name,
    resolve_production_ns,
)

logger = logging.getLogger(__name__)


def submit_simulation_job(
    sim_working_dir: str,
    sim_label: str,
    production_ns: Optional[float] = None,
    workflow_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Prepare and submit one SLURM job for *sim_working_dir*.

    Returns dict with success, job_id, job_script, error.
    """
    from src.hpc.job_submitter import submit_job
    from src.hpc.script_creator import create_slurm_script
    from src.hpc.file_copy import copy_simulation_files

    wd = Path(sim_working_dir)
    simsetup_dir = wd / "simsetup"
    hpc_dir = wd / "hpc"
    hpc_dir.mkdir(parents=True, exist_ok=True)

    ns = production_ns
    if ns is None:
        ns = resolve_production_ns(workflow_state, sim_label, sim_working_dir)

    from agentic.utils.conversation_logger import (
        log_agent_action,
        log_agent_completion,
        log_file_operation,
        set_log_file,
    )

    log_path = str(wd / "agent_conversation.log")
    set_log_file(log_path)
    log_agent_action(
        "hpc",
        f"HPC pool: prepare and submit SLURM job for {sim_label}",
        {
            "mode": "hpc_pool",
            "sim_label": sim_label,
            "simsetup_dir": str(simsetup_dir),
            "hpc_dir": str(hpc_dir),
            "production_ns": ns,
        },
    )

    copy_result = copy_simulation_files.func(
        source_dir=str(simsetup_dir),
        dest_dir=str(hpc_dir),
    )
    if not copy_result.get("success"):
        log_file_operation("hpc", "copy", str(hpc_dir), False, copy_result.get("error", ""))
        return {
            "success": False,
            "error": copy_result.get("error", "copy_simulation_files failed"),
        }
    log_file_operation(
        "hpc",
        "copy",
        str(hpc_dir),
        True,
        f"simsetup → hpc ({copy_result.get('files_copied', 'ok')})",
    )

    job_name = derive_job_name(sim_label, sim_working_dir)
    slurm_params = build_slurm_script_params(
        job_name=job_name,
        hpc_dir=str(hpc_dir),
        simsetup_dir=str(simsetup_dir),
        workflow_state=workflow_state,
    )
    log_agent_action(
        "hpc",
        "SLURM script parameters (pool mode)",
        {
            "job_name": job_name,
            "time_limit": slurm_params.get("time_limit"),
            "memory": slurm_params.get("memory"),
            "partition": slurm_params.get("partition"),
            "simulation_phases": slurm_params.get("simulation_phases"),
        },
    )

    script_result = create_slurm_script.func(**slurm_params)
    if not script_result.get("success"):
        log_agent_action(
            "hpc",
            "SLURM script creation failed",
            {"error": script_result.get("error", "create_slurm_script failed")},
        )
        return {
            "success": False,
            "error": script_result.get("error", "create_slurm_script failed"),
        }

    script_path = script_result.get("script_path") or script_result.get("output_path")
    if not script_path:
        candidates = sorted(hpc_dir.glob("*_run.sh")) + sorted(hpc_dir.glob("*.sh"))
        script_path = str(candidates[0]) if candidates else None
    if not script_path:
        return {"success": False, "error": "No SLURM script produced"}

    submit_result = submit_job.func(script_path=script_path)
    if not submit_result.get("success"):
        log_agent_action(
            "hpc",
            "SLURM submission failed",
            {"error": submit_result.get("error", "submit_job failed"), "script": script_path},
        )
        return {
            "success": False,
            "error": submit_result.get("error", "submit_job failed"),
            "job_script": script_path,
        }

    result = {
        "success": True,
        "job_id": submit_result.get("job_id"),
        "job_script": script_path,
        "job_name": job_name,
        "production_ns": ns,
        "time_limit": slurm_params.get("time_limit"),
        "message": submit_result.get("message"),
    }
    log_agent_action(
        "hpc",
        "Submitted SLURM job",
        {
            "job_id": result["job_id"],
            "job_script": script_path,
            "job_name": job_name,
            "mode": "hpc_pool",
            "production_ns": ns,
            "time_limit": slurm_params.get("time_limit"),
        },
    )
    log_agent_completion(
        "hpc",
        "HPC pool job submission",
        {
            "job_id": result["job_id"],
            "job_script": script_path,
            "job_name": job_name,
            "hpc_dir": str(hpc_dir),
            "production_ns": ns,
            "time_limit": slurm_params.get("time_limit"),
        },
        True,
    )
    return result
