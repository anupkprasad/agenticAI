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

# CLI agent names → internal subtask mapping handled by SimAgent.
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
        # Active agents for this pool phase (execution).
        "agent_list": agent_list,
        # Full CLI pipeline (logging / context); never drop analysis/reporter here.
        "pipeline_agent_list": list(
            state.get("pipeline_agent_list")
            or state.get("requested_agent_list")
            or [
                "preprocess",
                "simsetup",
                "hpcjob",
                "analysis",
                "reporter",
            ]
        ),
        "force_field": state.get("force_field", "amber99sb-ildn"),
        "water_model": state.get("water_model", "tip3p"),
        "use_llm": bool(state.get("use_llm", True)),
        "llm_model": state.get("llm_model", "gpt-oss:20b"),
        "llm_base_url": state.get("llm_base_url", "http://localhost:11434"),
        "llm_token_budget": state.get("llm_token_budget"),
        "llm_provider": state.get("llm_provider", "auto"),
        "multi_sim_base_dir": state.get("multi_sim_base_dir") or state.get("working_directory"),
        "production_ns": state.get("production_ns"),
        "extended_minimization": bool(state.get("extended_minimization", False)),
        "md_engine": state.get("md_engine", "gromacs"),
        "reuse_hpc": bool(state.get("reuse_hpc", False)),
        "rep_num": int(state.get("rep_num") or 1),
        "replicate_base_seed": int(state.get("replicate_base_seed") or 12345),
        # Component-case metadata — without this, workers treat source-PDB MG/ATP
        # as always-on and ATP-only cases incorrectly keep crystallographic ions.
        "sim_case": {
            "label": label,
            "case_id": sim_info.get("case_id"),
            "case_description": sim_info.get("case_description"),
            "case_directive": sim_info.get("case_directive"),
        },
    }


def _agent_list_for_phase(state: Dict[str, Any], default: List[str]) -> List[str]:
    agents = state.get("agent_list") or default
    return [a for a in agents if a in _CLI_AGENTS]


def _resolve_prep_goal(state: Dict[str, Any], sim_info: Dict[str, Any]) -> str:
    """Return the master-plan per-sim goal unchanged (no phase rewrite).

    Phase scope is enforced by ``agent_list`` / pool routing, not by mutating
    the scientific user goal — that caused confusing log mismatches.
    """
    master = (sim_info.get("prompt") or sim_info.get("setup_prompt") or "").strip()
    if master:
        return master
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
        try:
            from src.simsetup.md_env import ensure_md_toolchain

            ensure_md_toolchain()
        except Exception:
            pass

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
            usage_dir = job.get("multi_sim_base_dir") or working_dir
            llm = LLMClient(
                model=job.get("llm_model", "gpt-oss:20b"),
                base_url=job.get("llm_base_url"),
                token_budget=job.get("llm_token_budget"),
                working_dir=usage_dir,
                provider=job.get("llm_provider", "auto"),
            )

        workflow = MDWorkflow(llm_client=llm)
        agents = job.get("agent_list") or ["analysis", "reporter"]
        pipeline = job.get("pipeline_agent_list") or agents
        phase = job.get("phase") or ""
        if agents == ["reporter"]:
            subtask_type = "reporter_only"
        elif phase == "analysis" or set(agents) <= {"analysis", "reporter"}:
            # Force analysis-only semantics so workers never re-enter HPC wait
            # (goal text still mentions full MD / HPC under --reuse-hpc).
            subtask_type = "analysis_only"
        else:
            subtask_type = "multi_agent"
        config: Dict[str, Any] = {
            "working_directory": working_dir,
            "is_multi_simulation": False,
            "subtask_type": subtask_type,
            # Execute only this phase's agents…
            "agent_list": agents,
            "active_agent_list": agents,
            # …but keep the full campaign pipeline visible in state/logs.
            "pipeline_agent_list": pipeline,
            "pool_phase": phase,
            "force_field": job.get("force_field"),
            "water_model": job.get("water_model"),
            "use_llm": job.get("use_llm", True),
            "human_in_loop": False,
            "md_engine": job.get("md_engine", "gromacs"),
            "reuse_hpc": bool(job.get("reuse_hpc", False)),
        }
        if phase == "analysis" or set(agents) <= {"analysis", "reporter"}:
            # Hard-disable HPC pool in analysis/reporter workers. Leftover
            # reuse-hpc workers were sleeping forever in hpc_pool_wait.
            config["hpc_pool_disabled"] = True
            config["use_hpc_pool"] = False
            config["post_hpc_analysis_only"] = True
            config["hpc_pool_phase_complete"] = True
        if job.get("raw_pdb"):
            config["raw_pdb"] = job["raw_pdb"]
        if job.get("production_ns") is not None:
            config["production_ns"] = job["production_ns"]
        if job.get("extended_minimization"):
            config["extended_minimization"] = True
        if job.get("sim_case"):
            config["sim_case"] = job["sim_case"]
        config["rep_num"] = int(job.get("rep_num") or 1)
        config["replicate_base_seed"] = int(job.get("replicate_base_seed") or 12345)

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
