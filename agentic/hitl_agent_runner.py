"""
Run field-agent plan + execute cycles from HITL chat (mirrors normal workflow).

User tasks skip the planner supervisor; the field agent LLM builds a structured
JSON plan and executes all steps via the agent's tool executor. Logging uses the
same conversation logger as the normal analysis workflow (agent start, LLM
interaction, per-step actions, completion).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from agentic.hitl_router import (
    bind_agent_context,
    hitl_agent_output_directory,
    hitl_view_working_directory,
)
from agentic.utils import set_log_file

logger = logging.getLogger(__name__)


@dataclass
class HitlAgentRunResult:
    success: bool
    agent_key: str
    task: str
    message: str
    plan_steps: List[str] = field(default_factory=list)
    generated_files: List[str] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)
    execution_log: str = ""
    plan_json_path: str = ""


def run_hitl_agent_task(
    agent_key: str,
    task: str,
    state: Dict[str, Any],
    llm: Any,
) -> HitlAgentRunResult:
    """
    Route a HITL chat task through the field agent's plan + execute workflow.
    """
    combined = bool(state.get("hitl_view_combined") or state.get("hitl_combined_execute"))
    bind_agent_context(
        state,
        agent_key,
        sim_label=state.get("hitl_target_sim_label"),
        for_execution=True,
    )

    sim_root = hitl_view_working_directory(state)
    conversation_log = str(Path(sim_root) / "agent_conversation.log")
    set_log_file(conversation_log)

    if combined and agent_key == "analysis":
        return _run_combined_analysis_hitl(task, state, llm)
    if combined and agent_key == "reporter":
        return _run_combined_reporter_hitl(task, state, llm)

    if agent_key == "analysis":
        return _run_analysis_hitl_task(task, state, llm)

    return HitlAgentRunResult(
        success=False,
        agent_key=agent_key,
        task=task,
        message=(
            f"HITL in-chat execution for '{agent_key}' is not wired yet. "
            f"Use: run {agent_key}: {task}"
        ),
        )


def _run_combined_analysis_hitl(
    task: str,
    state: Dict[str, Any],
    llm: Any,
) -> HitlAgentRunResult:
    """Run combined cross-simulation analysis via LLM plan + execute (same as per-sim HITL)."""
    from agentic.analysis.analysis_agent import MDAnalysisAgent
    from agentic.utils import log_error

    state["hitl_combined_execute"] = True
    state.setdefault("multi_sim_phase", "combined_analysis")
    agent = MDAnalysisAgent(llm)
    try:
        analysis_dir = agent.init_for_hitl_execution(state)
        output = agent.run_hitl_analysis_workflow(task, state)
        result = output.result
        plan = output.plan

        files = list(result.generated_files.keys())
        steps = [f"{s.tool_name}: {s.name}" for s in plan.steps]
        plan_path = str(Path(analysis_dir) / "execution_plan.json")

        msg_lines = [
            f"Combined analysis complete ({len(steps)} step(s)).",
            f"Output directory: {analysis_dir}",
        ]
        if files:
            msg_lines.append("Generated files:")
            for f in files[:12]:
                msg_lines.append(f"  • {Path(f).name}")
            if len(files) > 12:
                msg_lines.append(f"  … and {len(files) - 12} more")
        if result.issues:
            msg_lines.append("Issues:")
            for issue in result.issues[:5]:
                msg_lines.append(f"  ⚠ {issue}")
        msg_lines.append(f"Plan: {plan_path}")
        msg_lines.append(f"Report: {analysis_dir}/execution_report.md")
        msg_lines.append(f"Log: {analysis_dir}/execution_log.txt")

        return HitlAgentRunResult(
            success=result.success,
            agent_key="analysis",
            task=task,
            message="\n".join(msg_lines),
            plan_steps=steps,
            generated_files=files,
            issues=result.issues,
            execution_log=result.execution_log,
            plan_json_path=plan_path,
        )
    except Exception as exc:
        logger.exception("HITL combined analysis failed")
        log_error("analysis.hitl_combined_task", exc, {"task": task})
        return HitlAgentRunResult(
            success=False,
            agent_key="analysis",
            task=task,
            message=f"Combined analysis failed: {exc}",
            issues=[str(exc)],
        )


def _run_combined_reporter_hitl(
    task: str,
    state: Dict[str, Any],
    llm: Any,
) -> HitlAgentRunResult:
    """Regenerate combined HTML report from HITL chat."""
    from agentic.reporter.reporter_agent import ReporterAgent

    state.setdefault("multi_sim_phase", "combined_reporter")
    agent = ReporterAgent(llm)
    try:
        prior = (state.get("reporter_instructions") or "").strip()
        state["reporter_instructions"] = (
            f"{prior}\n\nHITL combined report task:\n{task}".strip() if prior else task
        )
        state = agent._run_combined_report_via_llm(state)
        report = state.get("reporter_output")
        return HitlAgentRunResult(
            success=bool(report),
            agent_key="reporter",
            task=task,
            message=f"Combined report: {report or 'no output'}",
            generated_files=[Path(str(report)).name] if report else [],
        )
    except Exception as exc:
        logger.exception("HITL combined reporter failed")
        return HitlAgentRunResult(
            success=False,
            agent_key="reporter",
            task=task,
            message=f"Combined reporter failed: {exc}",
            issues=[str(exc)],
        )


def _run_analysis_hitl_task(
    task: str,
    state: Dict[str, Any],
    llm: Any,
) -> HitlAgentRunResult:
    from agentic.analysis.analysis_agent import MDAnalysisAgent
    from agentic.utils import log_error

    agent = MDAnalysisAgent(llm)
    try:
        analysis_dir = agent.init_for_hitl_execution(state)
        output = agent.run_hitl_analysis_workflow(task, state)
        result = output.result
        plan = output.plan

        files = list(result.generated_files.keys())
        steps = [f"{s.tool_name}: {s.name}" for s in plan.steps]
        plan_path = str(Path(analysis_dir) / "execution_plan.json")

        msg_lines = [
            f"Analysis complete ({len(steps)} step(s)).",
            f"Output directory: {analysis_dir}",
        ]
        if files:
            msg_lines.append("Generated files:")
            for f in files[:12]:
                msg_lines.append(f"  • {Path(f).name}")
            if len(files) > 12:
                msg_lines.append(f"  … and {len(files) - 12} more")
        if result.issues:
            msg_lines.append("Issues:")
            for issue in result.issues[:5]:
                msg_lines.append(f"  ⚠ {issue}")
        msg_lines.append(f"Plan: {plan_path}")
        msg_lines.append(f"Report: {analysis_dir}/execution_report.md")
        msg_lines.append(f"Log: {analysis_dir}/execution_log.txt")

        return HitlAgentRunResult(
            success=result.success,
            agent_key="analysis",
            task=task,
            message="\n".join(msg_lines),
            plan_steps=steps,
            generated_files=files,
            issues=result.issues,
            execution_log=result.execution_log,
            plan_json_path=plan_path,
        )
    except Exception as exc:
        logger.exception("HITL analysis task failed")
        log_error("analysis.hitl_task", exc, {"task": task})
        return HitlAgentRunResult(
            success=False,
            agent_key="analysis",
            task=task,
            message=f"HITL analysis failed: {exc}",
            issues=[str(exc)],
        )
