"""
Build and write base-level workflow run summaries (JSON + Markdown).
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


def _sim_status(sim: Dict[str, Any]) -> str:
    if sim.get("skipped"):
        return "skipped"
    if sim.get("success"):
        return "success"
    return "failed"


def _sim_succeeded(sim: Dict[str, Any]) -> bool:
    if sim.get("skipped"):
        return False
    if "success" in sim:
        return bool(sim["success"])
    return bool(
        sim.get("job_id")
        or sim.get("trajectory_path")
        or sim.get("topology")
        or sim.get("coordinates")
        or sim.get("analysis_results")
        or sim.get("reporter_output")
    )


def _expected_simulation_count(final_state: Dict[str, Any], pdb_list: List[str]) -> int:
    sim_prompts = final_state.get("sim_prompts") or []
    if sim_prompts:
        return len(sim_prompts)
    sim_dirs = final_state.get("sim_working_dirs") or []
    if sim_dirs:
        return len(sim_dirs)
    return len(pdb_list)


def build_run_summary(
    final_state: Dict[str, Any],
    *,
    working_dir: str,
    goal: str,
    pdb_list: Optional[List[str]] = None,
    config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Assemble a structured summary of a workflow run."""
    pdb_list = pdb_list or []
    config = config or {}
    completed = list(final_state.get("completed_sim_states") or [])
    is_multi = bool(final_state.get("is_multi_simulation"))
    total = _expected_simulation_count(final_state, pdb_list) if is_multi else 1

    simulations: List[Dict[str, Any]] = []
    if is_multi and completed:
        for sim in completed:
            status = _sim_status(sim)
            simulations.append(
                {
                    "label": sim.get("label"),
                    "status": status,
                    "success": _sim_succeeded(sim),
                    "skipped": bool(sim.get("skipped")),
                    "skip_reason": sim.get("skip_reason"),
                    "working_directory": sim.get("working_directory"),
                    "job_id": sim.get("job_id"),
                    "job_status": sim.get("job_status"),
                    "topology": sim.get("topology"),
                    "trajectory_path": sim.get("trajectory_path"),
                    "errors": sim.get("errors") or [],
                    "warnings": (sim.get("warnings") or [])[:5],
                }
            )
    elif is_multi:
        # Infer from sim_prompts when snapshots missing
        for sp in final_state.get("sim_prompts") or []:
            simulations.append(
                {
                    "label": sp.get("label"),
                    "status": "unknown",
                    "working_directory": sp.get("working_dir"),
                    "case_description": sp.get("case_description"),
                }
            )

    n_success = sum(1 for s in simulations if s.get("status") == "success" or s.get("success"))
    n_skipped = sum(1 for s in simulations if s.get("skipped") or s.get("status") == "skipped")
    n_failed = sum(1 for s in simulations if s.get("status") == "failed")
    if not simulations and completed:
        n_success = sum(1 for s in completed if _sim_succeeded(s))
        n_skipped = sum(1 for s in completed if s.get("skipped"))
        n_failed = len(completed) - n_success - n_skipped

    combined_dir = str(Path(working_dir) / "combinedAnalysis")
    analysis_dir = final_state.get("analysis_directory") or str(Path(working_dir) / "analysis")

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "working_directory": working_dir,
        "mode": "multi_simulation" if is_multi else "single_simulation",
        "goal": goal,
        "subtask": config.get("subtask") or final_state.get("subtask_type"),
        "source_pdbs": [Path(p).name for p in (final_state.get("pdb_list") or pdb_list)],
        "domain_context": final_state.get("domain_context"),
        "structure_request": final_state.get("structure_request"),
        "counts": {
            "total_simulations": total,
            "source_pdbs": len(final_state.get("pdb_list") or pdb_list),
            "completed_success": n_success,
            "skipped": n_skipped,
            "failed": n_failed,
            "snapshots_recorded": len(completed),
        },
        "simulations": simulations,
        "combined_analysis_dir": combined_dir if Path(combined_dir).exists() else None,
        "analysis_dir": analysis_dir if Path(analysis_dir).exists() else None,
        "reporter_output": final_state.get("reporter_output"),
        "final_report_present": bool(final_state.get("final_report")),
        "errors": list(final_state.get("errors") or [])[:20],
        "warnings": list(final_state.get("warnings") or [])[:20],
        "log_file": str(Path(working_dir) / "agent_conversation.log"),
        "execution_report": str(Path(working_dir) / "supervisor" / "execution_report.md"),
    }


def format_run_summary_terminal(summary: Dict[str, Any]) -> str:
    """Format summary for terminal display."""
    lines = [
        "=" * 60,
        "WORKFLOW RUN SUMMARY",
        "=" * 60,
    ]
    counts = summary.get("counts", {})
    mode = summary.get("mode", "unknown")
    lines.append(f"  Mode: {mode}")
    lines.append(f"  Working directory: {summary.get('working_directory')}")

    if mode == "multi_simulation":
        src = counts.get("source_pdbs", 0)
        total = counts.get("total_simulations", 0)
        if src and total > src:
            lines.append(
                f"  Simulations: {total} total "
                f"({src} source structure(s) × component cases)"
            )
        else:
            lines.append(f"  Simulations: {total} total")
        lines.append(f"  Succeeded: {counts.get('completed_success', 0)}")
        lines.append(f"  Skipped:   {counts.get('skipped', 0)}")
        lines.append(f"  Failed:    {counts.get('failed', 0)}")

        sims = summary.get("simulations") or []
        if sims:
            lines.append("")
            lines.append("  Per-simulation:")
            for sim in sims:
                label = sim.get("label", "?")
                status = sim.get("status", "unknown")
                icon = {"success": "✓", "skipped": "⊘", "failed": "✗"}.get(status, "?")
                line = f"    {icon} {label} — {status}"
                if sim.get("skip_reason"):
                    line += f" ({sim['skip_reason']})"
                elif sim.get("job_id"):
                    line += f" (job {sim['job_id']})"
                lines.append(line)
    else:
        err_n = len(summary.get("errors") or [])
        warn_n = len(summary.get("warnings") or [])
        lines.append(f"  Errors: {err_n}  |  Warnings: {warn_n}")

    if summary.get("domain_context"):
        lines.append("")
        lines.append("  Domain target:")
        for dl in summary["domain_context"].splitlines()[:4]:
            lines.append(f"    {dl}")

    if summary.get("combined_analysis_dir"):
        lines.append(f"  Combined analysis: {summary['combined_analysis_dir']}")
    if summary.get("reporter_output"):
        lines.append(f"  Report: {summary['reporter_output']}")

    lines.append("")
    lines.append(f"  Summary file: {Path(summary['working_directory']) / 'run_summary.md'}")
    lines.append(f"  Full log: {summary.get('log_file')}")
    lines.append("=" * 60)
    return "\n".join(lines)


def format_run_summary_markdown(summary: Dict[str, Any]) -> str:
    """Render run summary as Markdown."""
    counts = summary.get("counts", {})
    lines = [
        "# AgenticAI Workflow Run Summary",
        "",
        f"**Generated:** {summary.get('generated_at')}",
        f"**Mode:** {summary.get('mode')}",
        f"**Working directory:** `{summary.get('working_directory')}`",
        "",
        "## Goal",
        "",
        f"{summary.get('goal', '')}",
        "",
        "## Counts",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Total simulations | {counts.get('total_simulations', '—')} |",
        f"| Source PDBs | {counts.get('source_pdbs', '—')} |",
        f"| Succeeded | {counts.get('completed_success', 0)} |",
        f"| Skipped | {counts.get('skipped', 0)} |",
        f"| Failed | {counts.get('failed', 0)} |",
        "",
    ]

    if summary.get("domain_context"):
        lines.extend(["## Domain / Structure", "", summary["domain_context"], ""])

    sims = summary.get("simulations") or []
    if sims:
        lines.extend(["## Simulations", ""])
        for sim in sims:
            label = sim.get("label", "?")
            status = sim.get("status", "unknown")
            lines.append(f"### {label} — {status}")
            if sim.get("working_directory"):
                lines.append(f"- **Directory:** `{sim['working_directory']}`")
            if sim.get("job_id"):
                lines.append(f"- **Job ID:** {sim['job_id']}")
            if sim.get("topology"):
                lines.append(f"- **Topology:** `{sim['topology']}`")
            if sim.get("skip_reason"):
                lines.append(f"- **Skip reason:** {sim['skip_reason']}")
            if sim.get("errors"):
                lines.append("- **Errors:**")
                for err in sim["errors"][:5]:
                    lines.append(f"  - {err}")
            lines.append("")

    if summary.get("errors"):
        lines.extend(["## Global Errors", ""])
        for err in summary["errors"]:
            lines.append(f"- {err}")
        lines.append("")

    if summary.get("warnings"):
        lines.extend(["## Global Warnings", ""])
        for warn in summary["warnings"][:15]:
            lines.append(f"- {warn}")
        lines.append("")

    lines.extend(
        [
            "## Artifacts",
            "",
            f"- Log: `{summary.get('log_file')}`",
            f"- Execution report: `{summary.get('execution_report')}`",
        ]
    )
    if summary.get("combined_analysis_dir"):
        lines.append(f"- Combined analysis: `{summary['combined_analysis_dir']}`")
    if summary.get("reporter_output"):
        lines.append(f"- Reporter output: `{summary['reporter_output']}`")

    return "\n".join(lines)


def write_run_summary(working_dir: str, summary: Dict[str, Any]) -> Dict[str, str]:
    """Write run_summary.json and run_summary.md to the base working directory."""
    base = Path(working_dir)
    base.mkdir(parents=True, exist_ok=True)

    json_path = base / "run_summary.json"
    md_path = base / "run_summary.md"

    json_path.write_text(
        json.dumps(summary, indent=2, default=str),
        encoding="utf-8",
    )
    md_path.write_text(format_run_summary_markdown(summary), encoding="utf-8")

    return {"json": str(json_path), "markdown": str(md_path)}
