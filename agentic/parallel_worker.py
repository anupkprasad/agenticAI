"""
Isolated per-simulation workflow runner for parallel multi-sim execution.

Each worker process runs a single simulation's agent pipeline (prep or
analysis/reporter) without multi-sim orchestration state.
"""
from __future__ import annotations

import logging
import os
import shutil
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# CLI agent names → internal subtask mapping handled by run_agenticAIWork.
_CLI_AGENTS = frozenset({"preprocess", "simsetup", "hpcjob", "analysis", "reporter"})


def build_per_sim_job_spec(state: Dict[str, Any], sim_info: Dict[str, Any], *, phase: str) -> Dict[str, Any]:
    """Build a picklable job dict for ``run_per_sim_workflow``."""
    label = sim_info.get("label") or "sim"
    working_dir = sim_info.get("working_dir") or ""
    sim_pdb = sim_info.get("pdb") or sim_info.get("pdb_path") or ""

    if phase == "prep":
        agent_list = ["preprocess", "simsetup"]
        user_goal = _resolve_prep_goal(state, sim_info)
    else:
        wd = working_dir
        from agentic.multi_sim_progress import (
            per_sim_analysis_done_on_disk,
            per_sim_reporter_done_on_disk,
        )

        if wd and per_sim_analysis_done_on_disk(wd) and not per_sim_reporter_done_on_disk(wd):
            agent_list = ["reporter"]
        else:
            agent_list = _agent_list_for_phase(state, default=["analysis", "reporter"])
        user_goal = (
            sim_info.get("analysis_prompt")
            or sim_info.get("prompt")
            or state.get("user_goal", "")
        )

    return {
        "label": label,
        "working_dir": working_dir,
        "user_goal": user_goal,
        "raw_pdb": sim_pdb,
        "phase": phase,
        "agent_list": agent_list,
        "force_field": state.get("force_field", "amber99sb-ildn"),
        "water_model": state.get("water_model", "tip3p"),
        "use_llm": bool(state.get("use_llm", True)),
        "llm_model": state.get("llm_model", "gpt-oss:20b"),
        "llm_base_url": state.get("llm_base_url", "http://localhost:11434"),
        "production_ns": state.get("production_ns"),
        "extended_minimization": bool(state.get("extended_minimization", False)),
        "md_engine": state.get("md_engine", "gromacs"),
    }


def _agent_list_for_phase(state: Dict[str, Any], default: List[str]) -> List[str]:
    agents = state.get("agent_list") or default
    return [a for a in agents if a in _CLI_AGENTS]


def _resolve_prep_goal(state: Dict[str, Any], sim_info: Dict[str, Any]) -> str:
    master = (sim_info.get("prompt") or sim_info.get("setup_prompt") or "").strip()
    if master:
        return (
            "HPC pool — phase 1/3 (preprocess + simsetup only for this simulation). "
            "Full pipeline continues with parallel HPC (phase 2) then per-sim "
            "analysis/reporter (phase 3) and combined analysis.\n\n"
            "Workflow scope for this phase: preprocessing and simulation setup only. "
            "Do not run HPC submission, MD production, analysis, or reporting yet — "
            "the cross-simulation pool handles HPC and post-production work.\n\n"
            f"{master}"
        )
    label = sim_info.get("label") or "simulation"
    wdir = sim_info.get("working_dir") or ""
    return (
        f"Preprocess and set up MD for simulation {label} in {wdir}. "
        f"Original study goal: {state.get('user_goal_original') or state.get('user_goal', '')}"
    )


def _copy_pdb_if_needed(job: Dict[str, Any]) -> None:
    """Ensure PDB exists in the per-sim working directory for prep jobs."""
    sim_pdb = job.get("raw_pdb") or ""
    working_dir = job.get("working_dir") or ""
    if not sim_pdb or not working_dir:
        return
    if job.get("phase") != "prep":
        return
    dest = Path(working_dir) / Path(sim_pdb).name
    if dest.is_file():
        job["raw_pdb"] = str(dest)
        return
    src = Path(sim_pdb)
    if src.is_file():
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        job["raw_pdb"] = str(dest)


def run_per_sim_workflow(job: Dict[str, Any]) -> Dict[str, Any]:
    """
    Execute one simulation's workflow in an isolated process.

    Must remain a module-level function for ``ProcessPoolExecutor``.
    """
    label = job.get("label", "sim")
    working_dir = job.get("working_dir", "")
    result: Dict[str, Any] = {
        "success": False,
        "label": label,
        "working_dir": working_dir,
        "phase": job.get("phase"),
        "error": None,
        "workflow_status": None,
    }

    try:
        _copy_pdb_if_needed(job)
        log_path = str(Path(working_dir) / "agent_conversation.log")
        Path(working_dir).mkdir(parents=True, exist_ok=True)

        from agentic.utils.conversation_logger import set_log_file

        set_log_file(log_path)

        os.chdir(working_dir)

        from agentic.workflow import MDWorkflow
        from agentic.llm import LLMClient

        llm = None
        if job.get("use_llm"):
            llm = LLMClient(
                model=job.get("llm_model", "gpt-oss:20b"),
                base_url=job.get("llm_base_url"),
            )

        workflow = MDWorkflow(llm_client=llm)
        agents = job.get("agent_list") or ["analysis", "reporter"]
        subtask_type = "reporter_only" if agents == ["reporter"] else "multi_agent"
        config: Dict[str, Any] = {
            "working_directory": working_dir,
            "is_multi_simulation": False,
            "subtask_type": subtask_type,
            "agent_list": agents,
            "force_field": job.get("force_field"),
            "water_model": job.get("water_model"),
            "use_llm": job.get("use_llm", True),
            "human_in_loop": False,
            "md_engine": job.get("md_engine", "gromacs"),
        }
        if job.get("raw_pdb"):
            config["raw_pdb"] = job["raw_pdb"]
        if job.get("production_ns") is not None:
            config["production_ns"] = job["production_ns"]
        if job.get("extended_minimization"):
            config["extended_minimization"] = True

        final = workflow.run(job.get("user_goal", ""), config)
        status = final.get("workflow_status") or ""
        errors = final.get("errors") or []
        failed = bool(errors) or str(status).startswith("failed")
        result["success"] = not failed
        result["workflow_status"] = status
        if errors:
            result["error"] = "; ".join(str(e) for e in errors[:3])
    except Exception as exc:
        result["error"] = str(exc)
        result["traceback"] = traceback.format_exc()
        logger.exception("Parallel worker failed for %s: %s", label, exc)

    return result


def job_already_complete(job: Dict[str, Any]) -> bool:
    """True when disk artifacts show this job's phase is finished."""
    wd = job.get("working_dir") or ""
    phase = job.get("phase")
    if phase == "prep":
        from agentic.multi_sim_hpc_pool import _sim_setup_ready

        return _sim_setup_ready(wd)
    from agentic.multi_sim_progress import (
        per_sim_analysis_done_on_disk,
        per_sim_post_hpc_artifacts_ready,
        per_sim_reporter_done_on_disk,
    )

    agents = job.get("agent_list") or ["analysis", "reporter"]
    if agents == ["reporter"]:
        return per_sim_reporter_done_on_disk(wd)
    if set(agents) >= {"analysis", "reporter"}:
        return per_sim_post_hpc_artifacts_ready(wd)
    if "analysis" in agents:
        return per_sim_analysis_done_on_disk(wd)
    return False
