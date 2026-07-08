"""
MD Workflow Analysis Agent

Performs analysis of simulation outputs based on supervisor prompts.
Uses LLM to plan analysis steps and selects appropriate tools; includes
fallbacks when data or dependencies are unavailable.

Refactored to follow SimulationSetupAgent workflow pattern.
"""
import os
import re
import json
import logging
import shutil
from datetime import datetime
from typing import Dict, Any, Optional, List, FrozenSet, Set
from pathlib import Path

from ..state import MDState
from ..hitl_config import hitl_should_interact
from ..llm import LLMClient
from ..utils import (
    log_supervisor_routing, log_agent_start, log_llm_interaction,
    log_agent_action, log_file_operation, log_agent_completion, log_error,
    SecureFileManager, sanitize_tool_output_params
)
from ..utils.tool_prompt_format import format_tools_for_llm_prompt
from .schemas import (
    AnalysisPlan, AnalysisStep,
    AnalysisResult as AnalysisExecutionResult,
    AnalysisAgentInput, AnalysisAgentOutput
)
from .tools import AnalysisToolExecutor, get_tool_metadata, is_combined_analysis_tool
from ..planner.planning_guidelines import (
    detect_requested_metrics,
    detect_requested_metrics_union,
    detect_requested_metrics_for_sim,
    detect_classification_requested,
    classification_metric_groups_for_goal,
    get_classification_tool_guide,
    get_classification_per_sim_tool_guide,
    detect_com_distance_mode,
    collect_goal_texts_for_intent,
    resolve_sims_for_combined_metric,
    get_standard_output_filenames_block,
    get_com_distance_tool_guide,
    get_pca_fel_tool_guide,
    STANDARD_OUTPUT_FILES,
)

logger = logging.getLogger(__name__)

_CALC_TOOL_TO_METRIC: Dict[str, str] = {
    "calculate_rmsd": "rmsd",
    "calculate_rmsf": "rmsf",
    "calculate_radius_of_gyration": "rg",
    "analyze_energy": "energy",
    "calculate_sasa": "sasa",
    "calculate_dccm": "dccm",
    "analyze_secondary_structure": "dssp",
    "calculate_ligand_pocket_distance": "com",
    "calculate_com_distance": "com",
    "calculate_trajectory_pca": "pca",
    "calculate_free_energy_landscape": "fel",
    "analyze_fel_landscape_features": "fel",
    "export_fel_basin_structures": "fel",
    "calculate_protein_ligand_contacts": "contacts",
    "calculate_pocket_sasa": "pocket_sasa",
    "analyze_ligand_residence": "residence",
    "calculate_pocket_rmsf": "pocket_rmsf",
    "calculate_ligand_rmsf": "ligand_rmsf",
}

_PREP_TOOLS = frozenset({"wrap_trajectory", "run_complete_analysis"})

# Optional heavy deps (graceful fallback)
try:
    import MDAnalysis as mda  # type: ignore
    HAS_MDA = True
except Exception:
    HAS_MDA = False


class MDAnalysisAgent:
    """LLM-driven analysis agent that plans and executes analysis tasks."""

    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        self.llm = llm_client
        self.config_path = config_path or os.path.join(os.path.dirname(__file__), "config.yaml")
        self.config = self._load_config()
        self.tool_executor = None  # Initialized per execution
        self.file_manager = None  # Initialized per execution for state-specific file registry
        self.tool_executor = None
        logger.info("MD Analysis Agent initialized")

    def _load_config(self) -> Dict[str, Any]:
        import yaml
        if os.path.exists(self.config_path):
            with open(self.config_path, "r") as f:
                return yaml.safe_load(f) or {}
        logger.warning(f"Analysis config {self.config_path} not found; using defaults")
        return self._default_config()

    def _default_config(self) -> Dict[str, Any]:
        return {
            "metrics": ["rmsd", "rmsf", "energy"],
            "plots": True,
            "output_dir": "./working_dir/analysis",
            "use_mdanalysis": True,
        }

    def _is_combined_hitl_context(self, state: Optional[MDState] = None) -> bool:
        """True when HITL or workflow is at project-base cross-simulation scope."""
        if not state:
            return False
        return bool(
            state.get("hitl_view_combined")
            or state.get("hitl_combined_execute")
            or state.get("multi_sim_phase") in ("combined_analysis", "combined_reporter")
        )

    def _get_analysis_tool_metadata(self, state: Optional[MDState] = None) -> Dict[str, Dict[str, Any]]:
        """Tool metadata for LLM planning (includes combined tools at project base)."""
        working_dir = state.get("working_directory") if state else None
        include_combined = self._is_combined_hitl_context(state)
        return get_tool_metadata(
            working_directory=working_dir,
            include_combined=include_combined,
        )

    def _format_tools_list_for_prompt(self, tool_metadata: Dict[str, Dict[str, Any]]) -> str:
        """Alias for detailed tool formatting (kept for backward compatibility)."""
        return self._format_tools_list_detailed(tool_metadata)

    def _format_tools_list_detailed(self, tool_metadata: Dict[str, Dict[str, Any]]) -> str:
        """Format tool metadata (docstring Args/Returns only — no duplicate Parameters block)."""
        return format_tools_for_llm_prompt(tool_metadata)

    def _resolve_enriched_goal_for_planning(
        self,
        state: Optional[MDState],
        agent_input: Optional[AnalysisAgentInput] = None,
    ) -> str:
        """Per-simulation enriched goal from input validation (clearest analysis scope)."""
        if state and state.get("is_multi_simulation"):
            idx = state.get("current_sim_index", 0)
            sim_prompts = state.get("sim_prompts") or []
            if 0 <= idx < len(sim_prompts):
                stored = (sim_prompts[idx].get("enriched_prompt") or "").strip()
                if stored:
                    return stored
        candidates = (
            getattr(agent_input, "enriched_goal", None) if agent_input else None,
            (state or {}).get("enriched_prompt"),
            (state or {}).get("rephrased_goal"),
        )
        for candidate in candidates:
            text = (candidate or "").strip()
            if text:
                return text
        return ""

    def _format_goal_context_for_planning(
        self,
        agent_input: AnalysisAgentInput,
        state: Optional[MDState] = None,
    ) -> str:
        """User + enriched goals for analysis planning prompts."""
        enriched = self._resolve_enriched_goal_for_planning(state, agent_input)
        user_goal = (agent_input.user_goal or "").strip()
        if enriched and enriched != user_goal:
            return (
                f"- User Goal: {user_goal or 'Not specified'}\n"
                f"- Enriched User Goal (PRIMARY scope — plan every analysis listed here): "
                f"{enriched}"
            )
        if enriched:
            return f"- Enriched User Goal (PRIMARY scope): {enriched}"
        return f"- User Goal: {user_goal or 'Not specified'}"

    def _format_trajectory_input_block(self, agent_input: AnalysisAgentInput) -> str:
        """Explicit topology/trajectory basenames the LLM must use in tool_params."""
        topo_name = (
            Path(agent_input.topology_file).name
            if agent_input.topology_file
            else "md.tpr"
        )
        traj_name = (
            Path(agent_input.trajectory_file).name
            if agent_input.trajectory_file
            else "md.xtc"
        )
        return (
            "**Required input filenames (copy exactly into every calculate_*/analyze_* step):**\n"
            f"- topology_file: \"{topo_name}\"\n"
            f"- trajectory_file: \"{traj_name}\"\n"
        )

    def _get_per_sim_tool_scope_note(self, state: Optional[MDState] = None) -> str:
        """Tell the analysis LLM to stay within this simulation's scope."""
        if state and self._is_combined_hitl_context(state):
            return self._get_combined_hitl_scope_note()
        note = (
            "**SCOPE — THIS SIMULATION ONLY:**\n"
            "- Use only per-trajectory analysis tools listed below.\n"
            "- Do NOT call run_combined_*, plot_combined_overlay, collect_metric_files, "
            "or other cross-simulation tools.\n"
            "- Cross-simulation comparison runs automatically after all simulations finish.\n"
        )
        if state and state.get("is_multi_simulation"):
            idx = state.get("current_sim_index", 0)
            sim_prompts = state.get("sim_prompts") or []
            if 0 <= idx < len(sim_prompts):
                label = sim_prompts[idx].get("label")
                if label:
                    note += f"- Current simulation: {label}\n"
        return note

    def _get_combined_hitl_scope_note(self) -> str:
        return (
            "**SCOPE — COMBINED CROSS-SIMULATION (project base):**\n"
            "- Use cross-simulation tools: run_combined_*, plot_combined_overlay, "
            "collect_metric_files, compute_comparison_table.\n"
            "- When the user names specific proteins or simulations (e.g. JAK1 and TYK2 only), "
            "pass ONLY those sim_dirs and labels — do not include other simulations.\n"
            "- Plan ONLY the metrics and deliverables the user requested; do not add Rg, COM, "
            "DCCM, RMSD, or other analyses unless explicitly asked.\n"
            "- For overlay plots use run_combined_analysis with a metrics list (e.g. [\"rmsf\"] "
            "only) or collect_metric_files + plot_combined_overlay.\n"
            "- Per-trajectory calculate_* tools are for single-sim rerun; prefer combined tools here.\n"
        )

    def _format_combined_sim_context_for_hitl(self, state: MDState) -> str:
        """List simulation paths and display labels for combined HITL planning."""
        from agentic.reporter.reporter_agent import resolve_combined_sim_context
        from src.reporter.combined_reporter import _parse_label_name_map, apply_label_name_map

        sim_dirs, labels = resolve_combined_sim_context(state)
        if not sim_dirs:
            return ""
        text = " ".join(
            filter(
                None,
                [
                    state.get("user_goal_original"),
                    state.get("master_enriched_prompt"),
                    state.get("user_goal"),
                ],
            )
        )
        name_map = _parse_label_name_map(text)
        if name_map:
            labels = apply_label_name_map(labels, name_map)
        lines = ["**Available simulations (use these exact paths in sim_dirs):**"]
        for sim_dir, label in zip(sim_dirs, labels):
            lines.append(f"  - {label}: {sim_dir}")
        base = state.get("multi_sim_base_dir") or state.get("working_directory", ".")
        lines.append(
            f"**Combined output directory:** {Path(base) / 'analysis'} "
            "(use working_dir='.' in combined tool_params)"
        )
        return "\n".join(lines)

    def _normalize_hitl_plan_dict(self, plan_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Coerce LLM plan JSON to shapes expected by AnalysisPlan."""
        overview = plan_dict.get("overview", "")
        if isinstance(overview, list):
            plan_dict["overview"] = "; ".join(str(x) for x in overview)
        elif not isinstance(overview, str):
            plan_dict["overview"] = str(overview) if overview else "HITL analysis task"
        reasoning = plan_dict.get("reasoning", "")
        if not isinstance(reasoning, str):
            plan_dict["reasoning"] = str(reasoning) if reasoning else ""
        for key in ("potential_issues", "recommendations"):
            val = plan_dict.get(key)
            if val is None:
                plan_dict[key] = []
            elif not isinstance(val, list):
                plan_dict[key] = [str(val)]
        return plan_dict

    def _filter_sims_for_hitl_task(
        self,
        task: str,
        sim_dirs: List[str],
        labels: List[str],
        name_map: Optional[Dict[str, str]] = None,
    ) -> tuple:
        """Return sim_dirs/labels subset when the HITL task names specific proteins/sims."""
        task_lower = task.lower()
        matched_dirs: List[str] = []
        matched_labels: List[str] = []
        for sim_dir, label in zip(sim_dirs, labels):
            tokens = {label.lower(), Path(sim_dir).name.lower()}
            if name_map:
                for key, display in name_map.items():
                    if key.lower() in tokens or display.lower() in tokens:
                        tokens.update({key.lower(), display.lower()})
            if any(len(t) >= 3 and t in task_lower for t in tokens):
                matched_dirs.append(sim_dir)
                matched_labels.append(label)
        if matched_dirs:
            return matched_dirs, matched_labels
        return sim_dirs, labels

    def _resolve_combined_tool_sim_dirs(
        self,
        state: MDState,
        task: str,
        tool_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Fix sim_dirs/labels/working_dir for combined tools (ignore hallucinated paths)."""
        from agentic.reporter.reporter_agent import resolve_combined_sim_context
        from src.reporter.combined_reporter import _parse_label_name_map, apply_label_name_map

        sim_dirs, labels = resolve_combined_sim_context(state)
        text = " ".join(
            filter(
                None,
                [task, state.get("user_goal_original"), state.get("master_enriched_prompt")],
            )
        )
        name_map = _parse_label_name_map(text)
        if name_map:
            labels = apply_label_name_map(labels, name_map)
        sim_dirs, labels = self._filter_sims_for_hitl_task(task, sim_dirs, labels, name_map)
        params = dict(tool_params)
        params["sim_dirs"] = sim_dirs
        params["labels"] = labels
        params["working_dir"] = self.file_manager.agent_dir if self.file_manager else "."
        return params

    def _task_prefers_existing_combined_data(self, task: str) -> bool:
        lower = task.lower()
        return any(
            kw in lower
            for kw in (
                "already",
                "existing",
                "respective",
                "raw data",
                "just use",
                "from their",
                "from each",
                "only create",
                "overlay only",
                "plot only",
            )
        )

    def _sanitize_combined_hitl_plan(
        self,
        plan_dict: Dict[str, Any],
        state: MDState,
        task: str,
    ) -> Dict[str, Any]:
        """Drop per-sim recalc steps when data exists; fix combined tool paths/metrics."""
        if not self._is_combined_hitl_context(state):
            return plan_dict

        from agentic.reporter.reporter_agent import resolve_combined_sim_context
        from src.reporter.combined_reporter import _parse_label_name_map, apply_label_name_map

        sim_dirs, labels = resolve_combined_sim_context(state)
        text = " ".join(
            filter(
                None,
                [task, state.get("user_goal_original"), state.get("master_enriched_prompt")],
            )
        )
        name_map = _parse_label_name_map(text)
        if name_map:
            labels = apply_label_name_map(labels, name_map)
        sim_dirs, labels = self._filter_sims_for_hitl_task(task, sim_dirs, labels, name_map)

        requested = detect_requested_metrics(task) or frozenset()
        recalc = any(
            kw in task.lower()
            for kw in ("recalculate", "recompute", "re-run", "rerun", "from trajectory", "from scratch")
        )
        prefer_existing = not recalc and (
            self._task_prefers_existing_combined_data(task) or self._is_combined_hitl_context(state)
        )
        metrics = sorted(m for m in requested if m in {"rmsd", "rmsf", "rg", "energy", "sasa", "hbond"})
        if not metrics and "rmsf" in task.lower():
            metrics = ["rmsf"]

        new_steps: List[Dict[str, Any]] = []
        for step in plan_dict.get("steps") or []:
            tool = step.get("tool_name") or ""
            if prefer_existing and tool.startswith("calculate_"):
                continue
            if is_combined_analysis_tool(tool):
                params = dict(step.get("tool_params") or {})
                params["sim_dirs"] = sim_dirs
                params["labels"] = labels
                params["working_dir"] = "."
                if metrics:
                    params["metrics"] = metrics
                step = {**step, "tool_params": params}
                new_steps.append(step)
            elif not tool.startswith("calculate_"):
                new_steps.append(step)

        has_combined = any(is_combined_analysis_tool(s.get("tool_name", "")) for s in new_steps)
        if not has_combined and metrics:
            new_steps.append({
                "name": f"Combined {'/'.join(metrics)} overlay",
                "description": (
                    "Collect existing per-simulation analysis files and build cross-sim overlay plots."
                ),
                "tool_name": "run_combined_analysis",
                "tool_params": {
                    "sim_dirs": sim_dirs,
                    "labels": labels,
                    "working_dir": ".",
                    "metrics": metrics,
                },
                "reason": "User requested combined plot from existing per-sim analysis data.",
            })

        plan_dict["steps"] = new_steps
        return plan_dict

    def _create_combined_hitl_fallback_plan(
        self,
        agent_input: AnalysisAgentInput,
        state: MDState,
    ) -> AnalysisPlan:
        """Template plan for combined HITL — overlay existing per-sim analysis files."""
        task = agent_input.user_goal or state.get("hitl_chat_task") or ""
        requested = detect_requested_metrics(task) or frozenset()
        metrics = sorted(m for m in requested if m in {"rmsd", "rmsf", "rg", "energy", "sasa", "hbond"})
        if not metrics:
            metrics = ["rmsf"] if "rmsf" in task.lower() else ["rmsf"]

        from agentic.reporter.reporter_agent import resolve_combined_sim_context
        from src.reporter.combined_reporter import _parse_label_name_map, apply_label_name_map

        sim_dirs, labels = resolve_combined_sim_context(state)
        text = " ".join(
            filter(
                None,
                [task, state.get("user_goal_original"), state.get("master_enriched_prompt")],
            )
        )
        name_map = _parse_label_name_map(text)
        if name_map:
            labels = apply_label_name_map(labels, name_map)
        sim_dirs, labels = self._filter_sims_for_hitl_task(task, sim_dirs, labels, name_map)

        step = AnalysisStep(
            name=f"Combined {'/'.join(metrics)} overlay",
            description="Overlay existing per-simulation metric files at project base.",
            tool_name="run_combined_analysis",
            tool_params={
                "sim_dirs": sim_dirs,
                "labels": labels,
                "working_dir": ".",
                "metrics": metrics,
            },
            reason="Combined HITL fallback using on-disk per-sim analysis outputs.",
        )
        return AnalysisPlan(
            reasoning=f"Combined overlay from existing data for: {', '.join(labels)}",
            overview=f"Combined {'/'.join(metrics)} comparison for {', '.join(labels)}",
            steps=[step],
            potential_issues=["Missing metric files under sim/analysis/ will skip that simulation"],
            recommendations=["Verify rmsf.dat (or rmsf.png) exists in each sim analysis folder"],
        )

    def analysis_node(self, state: MDState) -> MDState:
        """
        Main analysis node - entry point from workflow.

        In multi-sim combined_analysis phase: runs cross-simulation overlay
        analysis using dedicated combined tools.
        Otherwise: runs the regular per-simulation LLM-guided analysis.
        """
        # ── Combined multi-sim analysis ───────────────────────────────────
        if state.get("multi_sim_phase") == "combined_analysis":
            return self._run_combined_analysis(state)

        # ── Regular per-sim analysis ──────────────────────────────────────
        execution_plan = state.get("execution_plan", {})
        has_planner_instructions = execution_plan.get("format") == "natural_language"
        
        input_summary = {
            "hpc_output_dir": state.get("hpc_output_directory"),
            "trajectory_file": state.get("trajectory_path"),
            "topology_file": state.get("topology")
        }
        
        if has_planner_instructions:
            # Prefer pre-extracted instructions from supervisor (avoids duplication)
            analysis_section = state.get("analysis_instructions")
            
            if not analysis_section:
                # Fallback: Extract from full plan if supervisor didn't provide it
                full_plan = execution_plan.get("full_plan", "")
                analysis_section = self._extract_agent_instructions(full_plan, "Analysis Agent")
            
            if analysis_section:
                input_summary["planner_instructions"] = analysis_section
            else:
                input_summary["planner_instructions"] = "[Natural language plan from planner]"
        else:
            # Fallback to user goal if no planner instructions
            input_summary["user_goal"] = state.get("user_goal")
        
        log_agent_start("analysis", "MD Trajectory Analysis with LLM Planning", input_summary)
        
        try:
            # Initialize secure file manager
            working_dir = state.get("working_directory", "working_dir")
            file_registry = state.get("file_registry", {})
            
            self.file_manager = SecureFileManager(
                working_dir=working_dir,
                agent_name="analysis",
                file_registry=file_registry
            )
            
            logger.info(f"Analysis agent directory: {self.file_manager.agent_dir}")
            
            # Get analysis directory from file manager (ensures consistency)
            analysis_dir = self.file_manager.agent_dir
            state["analysis_dir"] = analysis_dir
            state["analysis_directory"] = analysis_dir  # Backward compatibility
            
            self.tool_executor = AnalysisToolExecutor(config={
                "working_directory": analysis_dir,
                "include_combined_tools": False,
                "user_goal": state.get("user_goal_original") or state.get("user_goal", ""),
            })
            
            # Copy files from HPC output directory if needed (using secure file manager)
            self._copy_files_from_hpc_secure(state)

            # Wrap trajectory to fix PBC artefacts (runs by default; set
            # skip_pbc_wrap=True in state to disable for pre-wrapped trajectories)
            self._wrap_trajectory_pbc(state, analysis_dir)

            # Write PDB validation info to summary file if available from supervisor
            self._write_pdb_info_to_summary(state, analysis_dir)
            
            # Prepare agent input from state
            agent_input = self._prepare_agent_input(state)
            
            # Run LLM-guided analysis workflow
            agent_output = self._run_analysis_workflow(agent_input, state)
            
            # Update state with results
            self._update_state(state, agent_output)
            
            # Determine next workflow node
            if agent_output.success:
                # Clear any previous analysis-related errors from earlier retry attempts
                state["errors"] = [
                    e for e in state.get("errors", [])
                    if not (e.startswith("Analysis failed:") or e.startswith("Analysis error:"))
                ]
                if hitl_should_interact(state):
                    state["next_node"] = "human_analysis_check"
                else:
                    state["next_node"] = "supervisor"
            else:
                state["errors"].append(f"Analysis failed: {agent_output.result.report}")
                # Error-triggered HITL
                state["next_node"] = "human_analysis_check"
                state["error_triggered_hitl"] = True
            
            success = agent_output.success and len(agent_output.result.issues) == 0
            log_agent_completion("analysis", "MD Trajectory Analysis", state, success)
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Analysis agent failed: {e}")
            logger.error(f"Traceback: {tb}")
            log_error("analysis_agent.analysis_node", e, {"state": str(state), "traceback": tb})
            state["errors"].append(f"Analysis error: {str(e)}")
            # Error-triggered HITL
            state["next_node"] = "human_analysis_check"
            state["error_triggered_hitl"] = True
        
        return state

    # ── HITL in-chat task execution ─────────────────────────────────────

    def init_for_hitl_execution(self, state: MDState) -> str:
        """Initialize tool executor and paths for a HITL chat task (no graph routing)."""
        working_dir = state.get("working_directory", "working_dir")
        analysis_dir = (
            state.get("analysis_dir")
            or state.get("hitl_agent_output_directory")
            or str(Path(working_dir) / "analysis")
        )
        Path(analysis_dir).mkdir(parents=True, exist_ok=True)
        state["analysis_dir"] = analysis_dir
        state["analysis_directory"] = analysis_dir

        file_registry = state.get("file_registry") or {}
        self.file_manager = SecureFileManager(
            working_dir=working_dir,
            agent_name="analysis",
            file_registry=file_registry,
        )
        self.tool_executor = AnalysisToolExecutor(
            config={
                "working_directory": analysis_dir,
                "include_combined_tools": bool(
                    state.get("hitl_view_combined")
                    or state.get("multi_sim_phase") == "combined_analysis"
                    or state.get("hitl_combined_execute")
                ),
                "user_goal": state.get("user_goal_original") or state.get("user_goal", ""),
            }
        )
        self._copy_files_from_hpc_secure(state)
        if not state.get("skip_pbc_wrap"):
            self._wrap_trajectory_pbc(state, analysis_dir)

        resolved = self._resolve_input_files(state)
        if resolved.get("topology"):
            state["topology"] = resolved["topology"]
        if resolved.get("trajectory"):
            state["trajectory_path"] = resolved["trajectory"]
        if resolved.get("energy"):
            state["energy_file"] = resolved["energy"]
        if state.get("hpc_output_directory") is None:
            if self._is_combined_hitl_context(state):
                state["hpc_output_directory"] = ""
            else:
                state["hpc_output_directory"] = str(Path(working_dir) / "hpc")
        return analysis_dir

    def prepare_agent_input_for_hitl(self, state: MDState, task: str) -> AnalysisAgentInput:
        """Build agent input with the HITL chat task as the sole user goal (no planner merge)."""
        topology_file = state.get("topology")
        hpc_dir = (
            state.get("hpc_dir")
            or state.get("hpc_output_directory")
            or state.get("hpc_directory")
        )
        if not hpc_dir and not self._is_combined_hitl_context(state):
            hpc_dir = str(Path(state.get("working_directory", "working_dir")) / "hpc")
        hpc_dir = hpc_dir or ""
        if hpc_dir and topology_file:
            hpc_dir_path = Path(hpc_dir)
            candidate = hpc_dir_path / Path(topology_file).name
            if candidate.exists():
                topology_file = str(candidate)

        return AnalysisAgentInput(
            working_directory=state.get("working_directory", "working_dir"),
            hpc_output_dir=hpc_dir,
            topology_file=topology_file,
            trajectory_file=state.get("trajectory_path"),
            energy_file=state.get("energy_file"),
            analyses=[],
            user_goal=task,
            additional_instructions=None,
        )

    def run_hitl_analysis_workflow(self, task: str, state: MDState) -> AnalysisAgentOutput:
        """Plan + execute a HITL chat task using the same logging path as normal analysis."""
        state["hitl_chat_task"] = task
        input_summary = {
            "user_goal": task,
            "topology_file": state.get("topology"),
            "trajectory_file": state.get("trajectory_path"),
        }
        log_agent_start("analysis", "HITL Analysis Task", input_summary)

        try:
            agent_input = self.prepare_agent_input_for_hitl(state, task)
            plan = self._create_hitl_analysis_plan_llm(agent_input, state, task)

            log_agent_action("analysis", "Generated analysis plan", {
                "steps": len(plan.steps),
                "tools": [s.tool_name for s in plan.steps],
                "reasoning": plan.reasoning,
            })

            exec_plan = state.get("execution_plan") or {}
            exec_plan.setdefault("structured_plans", {})["analysis"] = plan.model_dump()
            state["execution_plan"] = exec_plan

            output = self.execute_plan_for_hitl(agent_input, plan, state)
            self._save_hitl_execution_artifacts(plan, output.result, task)

            success = output.success and len(output.result.issues) == 0
            log_agent_completion("analysis", "HITL Analysis Task", state, success)
            return output
        finally:
            state.pop("hitl_chat_task", None)

    def create_hitl_analysis_plan(
        self,
        agent_input: AnalysisAgentInput,
        state: MDState,
        task: str,
    ) -> AnalysisPlan:
        """LLM JSON plan for a HITL task (always fresh, not planner-derived)."""
        return self._create_hitl_analysis_plan_llm(agent_input, state, task)

    def execute_plan_for_hitl(
        self,
        agent_input: AnalysisAgentInput,
        plan: AnalysisPlan,
        state: MDState,
    ) -> AnalysisAgentOutput:
        """Execute plan and merge results into state (HITL chat context)."""
        result = self._execute_analysis_plan(agent_input, plan, state)
        output = AnalysisAgentOutput(
            success=result.success,
            plan=plan,
            result=result,
            supervisor_update={
                "analysis_results": result.results,
                "analysis_directory": state.get("analysis_directory"),
            },
        )
        self._update_state(state, output)
        return output

    def _create_hitl_analysis_plan_llm(
        self,
        agent_input: AnalysisAgentInput,
        state: MDState,
        task: str,
    ) -> AnalysisPlan:
        """LLM plan for HITL chat — task text only; no multisim intent filtering."""
        prompt = self._build_hitl_planning_prompt(task, agent_input, state)
        try:
            content = self.llm.prompt_raw(prompt, temperature=0.2, max_tokens=16384, format="json")

            log_llm_interaction(
                "analysis.hitl_planning",
                prompt,
                content,
                is_mock=hasattr(self.llm, "_is_mock_mode") and self.llm._is_mock_mode,
            )

            plan_dict = self._extract_plan_json(content)
            plan_dict = self._normalize_plan_steps(plan_dict, agent_input)
            plan_dict = self._normalize_hitl_plan_dict(plan_dict)
            plan_dict = self._sanitize_combined_hitl_plan(plan_dict, state, task)
            return AnalysisPlan(
                reasoning=plan_dict.get("reasoning", content[:500]),
                overview=plan_dict.get("overview", "HITL analysis task"),
                steps=[
                    AnalysisStep(
                        name=step.get("name", "unknown"),
                        description=step.get("description", ""),
                        tool_name=step.get("tool_name", ""),
                        tool_params=step.get("tool_params", {}),
                        reason=step.get("reason", ""),
                    )
                    for step in plan_dict.get("steps", [])
                ],
                potential_issues=plan_dict.get("potential_issues", []),
                recommendations=plan_dict.get("recommendations", []),
            )
        except Exception as exc:
            logger.warning("HITL LLM planning failed, using fallback: %s", exc)
            if self._is_combined_hitl_context(state):
                return self._create_combined_hitl_fallback_plan(agent_input, state)
            return self._create_fallback_analysis_plan(agent_input, state)

    def _build_hitl_planning_prompt(
        self,
        task: str,
        agent_input: AnalysisAgentInput,
        state: MDState,
    ) -> str:
        """Planning prompt where the HITL chat task is the only user intent."""
        tool_metadata = self._get_analysis_tool_metadata(state)
        tools_list_str = self._format_tools_list_detailed(tool_metadata)
        pdb_info_str = self._format_pdb_info_for_llm(state)
        input_files_block = self._format_trajectory_input_block(agent_input)

        topo_name = Path(agent_input.topology_file).name if agent_input.topology_file else "md.tpr"
        traj_name = Path(agent_input.trajectory_file).name if agent_input.trajectory_file else "mdWrap.xtc"

        scope_note = self._get_per_sim_tool_scope_note(state)
        combined_context = ""
        if self._is_combined_hitl_context(state):
            combined_context = self._format_combined_sim_context_for_hitl(state)

        return f"""You are the Analysis Agent in Human-in-the-Loop (HITL) mode.

**USER REQUEST (sole intent — ignore any prior workflow or multisim goals):**
{task}
{scope_note}
{combined_context}

**Available Data:**
- Topology File: {agent_input.topology_file or "Not available"} (use filename "{topo_name}" in tool_params)
- Trajectory File: {agent_input.trajectory_file or "Not available"} (use filename "{traj_name}" in tool_params)
- Energy File: {agent_input.energy_file or "Not available"}
{input_files_block}
{pdb_info_str}

**Available Tools:**
{tools_list_str}

**HITL PLANNING RULES:**
- Plan ONLY what the user requested above — do not add RMSF, Rg, RMSD, COM distance, or other metrics unless explicitly asked.
- Compound requests need multiple steps (one tool call per distinct deliverable).
- For DSSP / secondary structure:
  • Full protein: analyze_secondary_structure with selection="protein", output_prefix="dssp", create_heatmap=True
  • Residue segment (e.g. 100–120): a second analyze_secondary_structure with selection="protein and resid 100:120",
    output_prefix="dssp_res100_120", create_heatmap=True
  • analyze_secondary_structure generates heatmaps internally — do NOT add a separate plot step for DSSP heatmaps.
- For calculate_* metrics that produce .dat/.csv files, follow each with plot_md_data using the data filename only.
- For combined cross-simulation overlays: use run_combined_analysis with metrics limited to what the user asked
  (e.g. metrics=["rmsf"] only) and sim_dirs/labels restricted to the simulations the user named.
- Per-simulation metric files already live under each sim's analysis/ folder (e.g. rmsf.dat). For combined
  overlay requests, do NOT call calculate_rmsf/calculate_* — only run_combined_analysis (or collect_metric_files
  + plot_combined_overlay) using those existing files.
- Use the exact sim_dirs paths listed above — never invent paths from other projects.
- overview MUST be a single string (not a JSON array).

Output as JSON:
{{
  "reasoning": "How you will fulfill the user request",
  "overview": "High-level summary",
  "steps": [
    {{
      "name": "step name",
      "description": "what it does",
      "tool_name": "tool to call",
      "tool_params": {{"param": "value"}},
      "reason": "why this step is needed"
    }}
  ],
  "potential_issues": [],
  "recommendations": []
}}
"""

    def _save_hitl_execution_artifacts(
        self,
        plan: AnalysisPlan,
        result: AnalysisExecutionResult,
        task: str,
    ) -> None:
        """Persist execution_plan.json, execution_report.md, and execution_log.txt."""
        if not self.file_manager:
            return

        agent_dir = self.file_manager.agent_dir
        stamp = datetime.now().isoformat(timespec="seconds")

        plan_data = {
            "timestamp": stamp,
            "source": "hitl",
            "task": task,
            "reasoning": plan.reasoning,
            "overview": plan.overview,
            "steps": [
                {
                    "name": step.name,
                    "description": step.description,
                    "tool_name": step.tool_name,
                    "tool_params": step.tool_params,
                    "reason": step.reason,
                }
                for step in plan.steps
            ],
            "potential_issues": plan.potential_issues,
            "recommendations": plan.recommendations,
        }
        plan_file = os.path.join(agent_dir, "execution_plan.json")
        with open(plan_file, "w", encoding="utf-8") as fh:
            json.dump(plan_data, fh, indent=2)

        report = self._generate_execution_report(
            plan, result.results, result.issues, result.warnings
        )
        report_file = os.path.join(agent_dir, "execution_report.md")
        with open(report_file, "w", encoding="utf-8") as fh:
            fh.write(report + "\n")

        log_file = os.path.join(agent_dir, "execution_log.txt")
        step_lines = [
            f"  {i + 1}. {s.tool_name}: {s.name}" for i, s in enumerate(plan.steps)
        ]
        header = f"ANALYSIS EXECUTION — {stamp}\nTask: {task}\nSuccess: {result.success}\n"
        body = header + "Plan steps:\n" + "\n".join(step_lines) + "\n\n" + result.execution_log
        with open(log_file, "a", encoding="utf-8") as fh:
            fh.write("\n" + "=" * 72 + "\n" + body + "\n")

    # ── Combined multi-sim analysis ───────────────────────────────────────

    def _run_combined_analysis(self, state: MDState) -> MDState:
        """
        Run cross-simulation combined analysis.

        Collects per-sim data files, produces overlay plots and stats CSVs
        in ``{working_directory}/analysis/``, and stores the results in state
        so the reporter can embed them in the combined report.
        """
        from .tools import run_combined_analysis, collect_metric_files

        from agentic.multi_sim_paths import resolve_multi_sim_base_dir

        working_dir = resolve_multi_sim_base_dir(state)
        if state.get("is_multi_simulation"):
            state["multi_sim_base_dir"] = working_dir
            state["working_directory"] = working_dir
        analysis_dir = str(Path(working_dir) / "analysis")
        Path(analysis_dir).mkdir(parents=True, exist_ok=True)
        state["analysis_dir"] = analysis_dir
        state["analysis_directory"] = analysis_dir

        # Resolve per-sim directories and labels from completed_sim_states
        completed = state.get("completed_sim_states") or []
        sim_dirs: List[str] = []
        labels: List[str] = []
        seen_labels: set = set()
        for snap in completed:
            label = snap.get("label")
            wd = snap.get("working_directory")
            if not label or not wd or label in seen_labels:
                continue
            seen_labels.add(label)
            sim_dirs.append(wd)
            labels.append(label)

        # Fall back to sim_working_dirs from planner if no completed states yet
        if not sim_dirs:
            sim_dirs = state.get("sim_working_dirs") or []
            sim_prompts = state.get("sim_prompts") or []
            labels = [p.get("label", f"sim_{i}") for i, p in enumerate(sim_prompts)]

        # Apply protein name mapping from goal text (fallback for re-runs where
        # labels may still be raw UniProt IDs from a prior planner run).
        from src.reporter.combined_reporter import _parse_label_name_map, apply_label_name_map
        _nm_text = (
            (state.get("user_goal_original") or "")
            + " "
            + (state.get("master_enriched_prompt") or "")
            + " "
            + (state.get("user_goal", "") or "")
        )
        _name_map_a = _parse_label_name_map(_nm_text)
        if _name_map_a:
            labels = apply_label_name_map(labels, _name_map_a)
        _goal_text = _nm_text.strip()

        log_agent_start(
            "analysis",
            "Combined Multi-Simulation Analysis",
            {"sim_dirs": sim_dirs, "labels": labels, "output_dir": analysis_dir},
        )

        try:
            from .tools import (
                run_combined_dccm_analysis,
                run_combined_dccm_difference,
                run_combined_rmsf_segment_analysis,
                run_combined_com_distance_analysis,
                run_combined_binding_rmsf_overlay,
                pair_apo_holo_simulations,
                run_combined_rmsf_apo_holo_analysis,
                run_combined_dccm_apo_holo_analysis,
                run_combined_rmsf_segment_apo_holo_analysis,
            )

            # pair_apo_holo_simulations is a plain helper (not a @tool), so it
            # is called directly without .func.
            apo_holo_pairs = pair_apo_holo_simulations(
                sim_dirs=sim_dirs,
                labels=labels,
                label_name_map=_name_map_a or None,
                user_goal=_goal_text or None,
            )

            combined_plan_text = (
                (state.get("combined_analysis_plan") or "")
                + " "
                + (state.get("user_goal_original") or "")
                + " "
                + (state.get("master_enriched_prompt") or state.get("enriched_prompt") or "")
            ).lower()
            requested = detect_requested_metrics_union(
                state.get("combined_analysis_plan") or "",
                state.get("user_goal_original") or "",
                state.get("master_enriched_prompt") or "",
                state.get("enriched_prompt") or "",
            )
            if requested is None:
                # Fall back to keyword scan on plan text only (not sim metadata blobs).
                metric_patterns = {
                    "rmsd": [r"\brmsd\b", r"root mean square deviation"],
                    "rmsf": [r"\brmsf\b", r"root mean square fluctuation"],
                    "rg": [r"\brg\b", r"radius of gyration", r"\bgyration\b"],
                    "energy": [r"\benergy\b", r"\bedr\b"],
                    "dccm": [r"\bdccm\b", r"cross[-\s]?correlation", r"correlated motion"],
                    "com": [
                        r"\bcom\b",
                        r"center[-\s]?of[-\s]?mass",
                        r"centre[-\s]?of[-\s]?mass",
                        r"ligand[-\s]?pocket[-\s]?distance",
                        r"ligand_pocket_distance",
                    ],
                    "dssp": [r"\bdssp\b", r"secondary[-\s]?structure"],
                    "pocket_rmsf": [r"pocket\s+rmsf", r"pocket_rmsf"],
                    "ligand_rmsf": [r"ligand\s+rmsf", r"ligand_rmsf"],
                }
                requested = frozenset(
                    metric
                    for metric, patterns in metric_patterns.items()
                    if any(re.search(pattern, combined_plan_text) for pattern in patterns)
                ) or None

            class_groups = classification_metric_groups_for_goal(
                state.get("user_goal_original") or "",
                state.get("combined_analysis_plan") or "",
                state.get("master_enriched_prompt") or "",
                state.get("enriched_prompt") or "",
            )

            explicit_metrics_requested = bool(requested)
            broad_dynamics_request = any(
                phrase in combined_plan_text
                for phrase in (
                    "protein dynamics",
                    "dynamic behavior",
                    "dynamic behaviour",
                    "conformational dynamics",
                    "shared dynamics",
                    "dynamic patterns",
                )
            )

            if explicit_metrics_requested and requested:
                combined_metrics = [
                    m for m in ("rmsd", "rmsf", "rg", "energy") if m in requested
                ]
            elif broad_dynamics_request:
                combined_metrics = ["rmsd", "rmsf", "rg"]
                requested = frozenset({"rmsd", "rmsf", "rg", "dccm"})
            else:
                combined_metrics = []
                requested = requested or frozenset()

            # Skip all-simulation RMSF overlay when apo/holo pairs exist —
            # per-protein RMSF comparison is clearer for ligand-effect studies.
            if apo_holo_pairs and "rmsf" in combined_metrics:
                combined_metrics = [m for m in combined_metrics if m != "rmsf"]

            plots = []
            tables = []
            skipped = []
            for metric in combined_metrics:
                metric_dirs, metric_labels = self._sims_for_combined_metric(
                    state, sim_dirs, labels, metric,
                    label_name_map=_name_map_a or None,
                )
                if len(metric_dirs) < 2:
                    logger.info(
                        f"Combined {metric}: need ≥2 simulations; "
                        f"matched {metric_labels}"
                    )
                    skipped.append(metric)
                    continue
                result = run_combined_analysis.func(
                    sim_dirs=metric_dirs,
                    labels=metric_labels,
                    working_dir=analysis_dir,
                    metrics=[metric],
                )
                plots.extend(result.get("plots", []))
                tables.extend(result.get("tables", []))
                skipped.extend(result.get("skipped", []))

            if combined_metrics:
                log_agent_action(
                    agent_name="analysis",
                    action="Combined Analysis Complete",
                    details={
                        "metrics": combined_metrics,
                        "plots": plots,
                        "tables": tables,
                        "skipped": skipped,
                    },
                )
            else:
                log_agent_action(
                    agent_name="analysis",
                    action="Combined Analysis Base Metrics Skipped",
                    details={"reason": "No base overlay metrics requested"},
                )

            # ── Per-protein RMSF apo vs holo ──────────────────────────────
            rmsf_apo_holo_plots: list = []
            if apo_holo_pairs and "rmsf" in requested:
                try:
                    rmsf_ah = run_combined_rmsf_apo_holo_analysis.func(
                        sim_dirs=sim_dirs,
                        labels=labels,
                        working_dir=analysis_dir,
                        label_name_map=_name_map_a or None,
                        user_goal=_goal_text or None,
                    )
                    if rmsf_ah.get("success"):
                        rmsf_apo_holo_plots = rmsf_ah.get("plots", [])
                        plots.extend(rmsf_apo_holo_plots)
                        log_agent_action(
                            "analysis", "Per-protein RMSF apo/holo comparison",
                            {"plots": rmsf_apo_holo_plots, "pairs": apo_holo_pairs},
                        )
                    else:
                        logger.info(f"RMSF apo/holo: {rmsf_ah.get('message')}")
                except Exception as _exc:
                    logger.warning(f"RMSF apo/holo comparison failed: {_exc}")

            # ── DCCM: per-protein apo | holo | Δ triptychs ────────────────
            dccm_plots: list = []

            if "dccm" in requested and apo_holo_pairs:
                try:
                    dccm_ah = run_combined_dccm_apo_holo_analysis.func(
                        sim_dirs=sim_dirs,
                        labels=labels,
                        working_dir=analysis_dir,
                        plot_mode="with_matrices",
                        label_name_map=_name_map_a or None,
                        user_goal=_goal_text or None,
                    )
                    if dccm_ah.get("success"):
                        dccm_plots = dccm_ah.get("plots", [])
                        log_agent_action(
                            "analysis", "Per-protein DCCM apo/holo triptychs",
                            {"plots": dccm_plots, "pairs": apo_holo_pairs},
                        )
                    else:
                        logger.warning(f"DCCM apo/holo: {dccm_ah.get('message')}")
                except Exception as _exc:
                    logger.warning(f"DCCM apo/holo analysis failed: {_exc}")
            elif "dccm" in requested:
                dccm_dirs, dccm_labels = self._sims_for_combined_metric(
                    state, sim_dirs, labels, "dccm", label_name_map=_name_map_a or None,
                )
                if len(dccm_dirs) < 2:
                    logger.info(
                        "DCCM comparison skipped: need ≥2 simulations with per-sim DCCM "
                        f"in their goals; matched {dccm_labels}"
                    )
                else:
                    try:
                        dccm_cmp = run_combined_dccm_analysis.func(
                            sim_dirs=dccm_dirs,
                            labels=dccm_labels,
                            working_dir=analysis_dir,
                            output_file="dccm_comparison.png",
                        )
                        if dccm_cmp.get("success"):
                            dccm_plots.append(dccm_cmp["output_path"])
                            log_agent_action(
                                "analysis", "DCCM comparison generated",
                                {
                                    "output": dccm_cmp.get("output_path"),
                                    "simulations": dccm_labels,
                                },
                            )
                        else:
                            logger.warning(f"DCCM comparison: {dccm_cmp.get('message')}")
                    except Exception as _exc:
                        logger.warning(f"DCCM comparison failed: {_exc}")

            # ── RMSF segment bar plots (from user-specified residue ranges) ─
            segment_plots: list = []
            try:
                if "rmsf" not in requested:
                    rmsf_seg = {"success": False, "message": "RMSF was not requested"}
                elif apo_holo_pairs:
                    rmsf_seg = run_combined_rmsf_segment_apo_holo_analysis.func(
                        sim_dirs=sim_dirs,
                        labels=labels,
                        working_dir=analysis_dir,
                        user_goal=_goal_text,
                        segments=state.get("rmsf_segments"),
                        label_name_map=_name_map_a or None,
                    )
                else:
                    rmsf_seg = run_combined_rmsf_segment_analysis.func(
                        sim_dirs=sim_dirs,
                        labels=labels,
                        working_dir=analysis_dir,
                        user_goal=_goal_text,
                        segments=state.get("rmsf_segments"),
                    )
                if rmsf_seg.get("success"):
                    segment_plots = rmsf_seg.get("plots", [])
                    plots.extend(segment_plots)
                    log_agent_action(
                        "analysis", "RMSF segment bar plots generated",
                        {"plots": segment_plots, "segments": rmsf_seg.get("segments", [])},
                    )
                else:
                    logger.info(f"RMSF segments: {rmsf_seg.get('message')}")
            except Exception as _exc:
                logger.warning(f"RMSF segment analysis failed: {_exc}")

            # ── ATP–pocket COM distance overlay (apo vs holo) ───────────────
            com_plot: Optional[str] = None
            try:
                if "com" not in requested:
                    com_result = {"success": False, "message": "COM distance was not requested"}
                else:
                    com_dirs, com_labels = self._sims_for_combined_metric(
                        state, sim_dirs, labels, "com",
                        label_name_map=_name_map_a or None,
                    )
                    com_result = run_combined_com_distance_analysis.func(
                        sim_dirs=com_dirs,
                        labels=com_labels,
                        working_dir=analysis_dir,
                    )
                if com_result.get("success"):
                    com_plot = com_result.get("output_path")
                    if com_plot and com_plot not in plots:
                        plots.append(com_plot)
                    found_com_files = com_result.get("found_files") or []
                    if len(found_com_files) >= 2:
                        try:
                            from .tools import compute_comparison_table
                            com_labels = []
                            for fpath in found_com_files:
                                sim_root = str(Path(fpath).parent.parent)
                                idx = sim_dirs.index(sim_root) if sim_root in sim_dirs else -1
                                com_labels.append(
                                    labels[idx] if 0 <= idx < len(labels) else Path(sim_root).name
                                )
                            table_result = compute_comparison_table.func(
                                data_files=found_com_files,
                                labels=com_labels,
                                output_csv="ligand_pocket_distance_stats.csv",
                                working_dir=analysis_dir,
                            )
                            com_table = table_result.get("output_path") or table_result.get("output_file")
                            if com_table and com_table not in tables:
                                tables.append(com_table)
                        except Exception as table_exc:
                            logger.warning(f"COM comparison table failed: {table_exc}")
                    log_agent_action(
                        "analysis", "COM distance overlay generated",
                        {
                            "output": com_plot,
                            "found": com_result.get("found_files", []),
                            "missing": com_result.get("missing", []),
                        },
                    )
                else:
                    logger.info(f"COM distance overlay: {com_result.get('message')}")
            except Exception as _exc:
                logger.warning(f"COM distance overlay failed: {_exc}")

            # ── Pocket / ligand RMSF combined overlays ───────────────────────
            overlay_metrics = set(requested or [])
            if class_groups is not None:
                overlay_metrics |= set(class_groups)
            for profile_type in ("pocket_rmsf", "ligand_rmsf"):
                if profile_type not in overlay_metrics:
                    continue
                try:
                    rmsf_dirs, rmsf_labels = self._sims_for_combined_metric(
                        state, sim_dirs, labels, profile_type,
                        label_name_map=_name_map_a or None,
                    )
                    if len(rmsf_dirs) < 1:
                        logger.info(
                            "Combined %s: no holo simulations with data", profile_type
                        )
                        continue
                    display_labels = [
                        (_name_map_a or {}).get(lab.lower(), lab)
                        for lab in rmsf_labels
                    ]
                    rmsf_overlay = run_combined_binding_rmsf_overlay.func(
                        sim_dirs=rmsf_dirs,
                        labels=display_labels,
                        working_dir=analysis_dir,
                        profile_type=profile_type,
                    )
                    if rmsf_overlay.get("success"):
                        out_path = rmsf_overlay.get("output_path")
                        if out_path and out_path not in plots:
                            plots.append(out_path)
                        log_agent_action(
                            "analysis",
                            f"Combined {profile_type} overlay generated",
                            {
                                "output": out_path,
                                "n_simulations": rmsf_overlay.get("n_simulations"),
                                "missing": rmsf_overlay.get("missing", []),
                            },
                        )
                    else:
                        logger.info(
                            "Combined %s overlay: %s",
                            profile_type,
                            rmsf_overlay.get("message") or rmsf_overlay.get("error"),
                        )
                except Exception as _exc:
                    logger.warning(f"Combined {profile_type} overlay failed: {_exc}")

            # ── DSSP: backfill missing per-sim runs, comparison chart, activation-loop heatmaps ─
            dssp_plots: list = []
            try:
                if "dssp" not in requested:
                    dssp_result = {"success": False, "message": "DSSP was not requested"}
                else:
                    from src.reporter.combined_reporter import run_combined_dssp_analysis
                    dssp_result = run_combined_dssp_analysis(
                        sim_dirs=sim_dirs,
                        labels=labels,
                        output_dir=analysis_dir,
                        user_goal=_goal_text,
                    )
                dssp_plots = dssp_result.get("plots", [])
                if dssp_plots:
                    plots.extend(p for p in dssp_plots if p not in plots)
                    log_agent_action(
                        "analysis", "Combined DSSP analysis",
                        {
                            "comparison": dssp_result.get("comparison_plot"),
                            "n_heatmaps": len(dssp_result.get("activation_loop_heatmaps", [])),
                            "backfilled": dssp_result.get("backfill", {}).get("backfilled", []),
                        },
                    )
                elif dssp_result.get("backfill", {}).get("errors"):
                    logger.warning(
                        "Combined DSSP: %s", dssp_result["backfill"]["errors"]
                    )
            except Exception as _exc:
                logger.warning(f"Combined DSSP analysis failed: {_exc}")

            # ── Phylogenetic trees (sequence / structure) — only on request ──
            try:
                from agentic.planner.planning_guidelines import (
                    detect_phylo_tree_requested,
                )

                phylo_req = detect_phylo_tree_requested(
                    state.get("user_goal_original") or "",
                    state.get("combined_analysis_plan") or "",
                    state.get("master_enriched_prompt")
                    or state.get("enriched_prompt")
                    or "",
                )
                if phylo_req.get("sequence") or phylo_req.get("structure"):
                    from .tools import (
                        build_sequence_phylo_tree,
                        build_structure_phylo_tree,
                    )

                    if phylo_req.get("sequence"):
                        seq_tree = build_sequence_phylo_tree.func(
                            sim_dirs=sim_dirs,
                            labels=labels,
                            working_dir=analysis_dir,
                            base_dir=working_dir,
                            label_name_map=_name_map_a or None,
                            user_goal=_goal_text,
                        )
                        if seq_tree.get("success") and seq_tree.get("plot_path"):
                            if seq_tree["plot_path"] not in plots:
                                plots.append(seq_tree["plot_path"])
                            log_agent_action(
                                "analysis",
                                "Sequence phylogenetic tree generated",
                                {
                                    "output": seq_tree.get("plot_path"),
                                    "n_sequences": seq_tree.get("n_sequences"),
                                    "missing": seq_tree.get("missing", []),
                                },
                            )
                        else:
                            logger.warning(
                                "Sequence phylo tree: %s",
                                seq_tree.get("error") or seq_tree.get("message"),
                            )

                    if phylo_req.get("structure"):
                        struct_tree = build_structure_phylo_tree.func(
                            sim_dirs=sim_dirs,
                            labels=labels,
                            working_dir=analysis_dir,
                            base_dir=working_dir,
                            label_name_map=_name_map_a or None,
                            user_goal=_goal_text,
                        )
                        if struct_tree.get("success") and struct_tree.get("plot_path"):
                            if struct_tree["plot_path"] not in plots:
                                plots.append(struct_tree["plot_path"])
                            log_agent_action(
                                "analysis",
                                "Structure phylogenetic tree generated",
                                {
                                    "output": struct_tree.get("plot_path"),
                                    "n_structures": struct_tree.get("n_structures"),
                                    "missing": struct_tree.get("missing", []),
                                },
                            )
                        else:
                            logger.warning(
                                "Structure phylo tree: %s",
                                struct_tree.get("error") or struct_tree.get("message"),
                            )
            except Exception as _exc:
                logger.warning(f"Phylogenetic tree analysis failed: {_exc}")

            # ── Classification feature matrix (only when user explicitly requests) ─
            classification_table = None
            classification_clustering = None
            if class_groups is not None:
                try:
                    from .tools import (
                        collect_classification_features_table,
                        cluster_classification_features,
                    )
                    from src.analysis.classification_clustering import (
                        clustering_method_for_goal,
                        plot_cluster_feature_trajectories,
                        plot_cluster_rmsf_profiles,
                        CLUSTER_TRAJECTORY_METRIC_GROUPS,
                        CLUSTER_RMSF_PROFILE_GROUPS,
                    )

                    class_result = collect_classification_features_table.func(
                        base_directory=working_dir,
                        working_dir=analysis_dir,
                        requested_metric_groups=sorted(class_groups),
                        allowed_labels=[Path(d).name for d in sim_dirs],
                    )
                    if class_result.get("success"):
                        classification_table = class_result.get("output_file")
                        tables.append(classification_table)
                        zscore_path = class_result.get("zscore_output_file")
                        if zscore_path:
                            tables.append(zscore_path)
                        log_agent_action(
                            "analysis",
                            "Classification feature table built",
                            {
                                "output": classification_table,
                                "metric_groups": sorted(class_groups),
                                "n_simulations": class_result.get("n_simulations"),
                            },
                        )

                        user_goal_text = " ".join(
                            t
                            for t in (
                                state.get("user_goal_original"),
                                state.get("user_goal"),
                                state.get("combined_analysis_plan"),
                                state.get("master_enriched_prompt"),
                                state.get("enriched_prompt"),
                            )
                            if t
                        ).strip()
                        cluster_method = clustering_method_for_goal(
                            user_goal_text,
                            state.get("combined_analysis_plan") or "",
                        )
                        cluster_result = cluster_classification_features.func(
                            working_dir=analysis_dir,
                            features_file=(
                                Path(zscore_path).name
                                if zscore_path
                                else "classification_features_zscore.csv"
                            ),
                            method=cluster_method,
                            user_goal=user_goal_text,
                            label_name_map=_name_map_a or None,
                        )
                        if cluster_result.get("success"):
                            classification_clustering = cluster_result
                            scatter = cluster_result.get("scatter_plot")
                            dendro = cluster_result.get("dendrogram_plot")
                            phylo = cluster_result.get("phylo_tree_plot")
                            if scatter:
                                plots.append(scatter)
                            if dendro:
                                plots.append(dendro)
                            if phylo:
                                plots.append(phylo)
                            log_agent_action(
                                "analysis",
                                "Classification clustering complete",
                                {
                                    "method": cluster_result.get("method"),
                                    "n_clusters": cluster_result.get("n_clusters"),
                                    "assignments": cluster_result.get("assignments_file"),
                                },
                            )
                            traj_groups = sorted(
                                g
                                for g in class_groups
                                if g in CLUSTER_TRAJECTORY_METRIC_GROUPS
                            )
                            if traj_groups:
                                traj_result = plot_cluster_feature_trajectories.func(
                                    working_dir=analysis_dir,
                                    assignments_file=(
                                        Path(cluster_result["assignments_file"]).name
                                        if cluster_result.get("assignments_file")
                                        else "classification_cluster_assignments.csv"
                                    ),
                                    metric_groups=traj_groups,
                                )
                                if traj_result.get("success"):
                                    for p in traj_result.get("plots", []):
                                        if p not in plots:
                                            plots.append(p)
                                    log_agent_action(
                                        "analysis",
                                        "Cluster trajectory plots generated",
                                        {
                                            "metrics": traj_result.get("metrics_plotted"),
                                            "n_clusters": traj_result.get("n_clusters"),
                                        },
                                    )
                                else:
                                    logger.warning(
                                        "Cluster trajectory plots: %s",
                                        traj_result.get("error"),
                                    )
                            rmsf_profile_types = sorted(
                                g
                                for g in class_groups
                                if g in CLUSTER_RMSF_PROFILE_GROUPS
                            )
                            if rmsf_profile_types:
                                rmsf_cluster = plot_cluster_rmsf_profiles.func(
                                    working_dir=analysis_dir,
                                    assignments_file=(
                                        Path(cluster_result["assignments_file"]).name
                                        if cluster_result.get("assignments_file")
                                        else "classification_cluster_assignments.csv"
                                    ),
                                    profile_types=rmsf_profile_types,
                                )
                                if rmsf_cluster.get("success"):
                                    for p in rmsf_cluster.get("plots", []):
                                        if p not in plots:
                                            plots.append(p)
                                    log_agent_action(
                                        "analysis",
                                        "Cluster RMSF profile plots generated",
                                        {
                                            "profiles": rmsf_cluster.get("profiles_plotted"),
                                            "n_clusters": rmsf_cluster.get("n_clusters"),
                                        },
                                    )
                                else:
                                    logger.warning(
                                        "Cluster RMSF plots: %s",
                                        rmsf_cluster.get("error"),
                                    )
                        else:
                            logger.warning(
                                "Classification clustering: %s",
                                cluster_result.get("error"),
                            )
                    else:
                        logger.warning(
                            "Classification table: %s", class_result.get("error")
                        )
                        log_agent_action(
                            "analysis",
                            "Classification feature table failed",
                            {"error": class_result.get("error"), "metric_groups": sorted(class_groups)},
                        )
                except Exception as _exc:
                    logger.warning(f"Classification feature table failed: {_exc}")
                    log_agent_action(
                        "analysis",
                        "Classification feature table failed",
                        {"error": str(_exc), "metric_groups": sorted(class_groups)},
                    )

            # Store results in state for the reporter
            analysis_results = state.get("analysis_results") or {}
            analysis_results["combined"] = {
                "sim_dirs": sim_dirs,
                "labels": labels,
                "overlay_plots": plots,
                "stats_tables": tables,
                "skipped_metrics": skipped,
                "dccm_plots": dccm_plots,
                "rmsf_apo_holo_plots": rmsf_apo_holo_plots,
                "apo_holo_pairs": apo_holo_pairs,
                "rmsf_segment_plots": segment_plots,
                "com_distance_plot": com_plot,
                "dssp_plots": dssp_plots,
                "classification_features_table": classification_table,
                "classification_clustering": classification_clustering,
                "classification_metric_groups": sorted(class_groups) if class_groups else None,
                "analysis_dir": analysis_dir,
            }
            state["analysis_results"] = analysis_results
            state["figures"] = (
                list(state.get("figures") or []) + plots + dccm_plots
            )

            state["errors"] = [
                e for e in state.get("errors", [])
                if not (e.startswith("Analysis failed:") or e.startswith("Analysis error:"))
            ]

            log_agent_completion("analysis", "Combined Multi-Simulation Analysis", state, True)
            if hitl_should_interact(state):
                state["next_node"] = "human_analysis_check"
            else:
                state["next_node"] = "supervisor"

        except Exception as exc:
            import traceback
            logger.error(f"Combined analysis failed: {exc}\n{traceback.format_exc()}")
            state["errors"].append(f"Combined analysis error: {exc}")
            state["next_node"] = "human_analysis_check"
            state["error_triggered_hitl"] = True

        return state

    def _extract_agent_instructions(self, full_plan: str, agent_name: str) -> Optional[str]:
        """
        Extract agent-specific detailed instructions from planner's natural language plan.
        
        Args:
            full_plan: Complete natural language plan from planner
            agent_name: Name of the agent section to extract (e.g., "Analysis Agent")
            
        Returns:
            Extracted instructions for this specific agent, or full plan as fallback
        """
        import re
        
        # Try multiple patterns to find the agent section (in priority order)
        patterns = [
            # New standardized format: **Analysis Agent:**
            rf'\*\*Analysis Agent:\*\*\s*\n(.*?)(?=\n\s*\*\*Expected Outcomes:|$)',
            # With optional colon
            rf'\*\*{agent_name}\*\*:?\s*\n(.*?)(?=\n\s*\*\*[A-Z]|\Z)',
            # Markdown headings
            rf'###\s*{agent_name}.*?\n(.*?)(?=###|\Z)',
            rf'##\s*{agent_name}.*?\n(.*?)(?=##|\Z)',
            # Fuzzy match patterns (allow for variations like "MD Analysis Agent")
            rf'\*\*(?:MD\s*)?Analysis.*?Agent\*\*:?\s*\n(.*?)(?=\n\s*\*\*[A-Z]|\Z)',
            rf'###\s*(?:MD\s*)?Analysis.*?Agent.*?\n(.*?)(?=###|\Z)',
            rf'##\s*(?:MD\s*)?Analysis.*?Agent.*?\n(.*?)(?=##|\Z)',
            # Section number patterns
            rf'\d+\..*?(?:MD\s*)?Analysis.*?Agent.*?\n(.*?)(?=\d+\.|\Z)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE)
            if match:
                instructions = match.group(1).strip()
                if len(instructions) > 50:  # Ensure we got substantial content
                    logger.info(f"Extracted {len(instructions)} chars of detailed instructions for {agent_name}")
                    return instructions
        
        # Fallback: Use full plan if no specific section found
        logger.info(f"Could not find specific section for {agent_name}, using full plan as context")
        logger.info(f"Full plan length: {len(full_plan)} chars")
        
        # Return full plan so agent still has context
        return full_plan

    def _copy_files_from_hpc_secure(self, state: MDState):
        """Copy trajectory and topology files from HPC using SecureFileManager."""
        # Get all HPC files from registry
        hpc_files = []
        for file_path, metadata in self.file_manager.file_registry.items():
            if metadata.get("stage") == "hpc" and Path(file_path).exists():
                hpc_files.append((file_path, metadata))
        
        if not hpc_files:
            logger.info("No HPC files found in registry to copy")
            return
        
        # Copy each HPC file to analysis directory using file manager
        for file_path, metadata in hpc_files:
            filename = Path(file_path).name
            file_type = metadata.get("type", "unknown")
            description = metadata.get("description", "HPC output file")
            
            # Use secure copy (automatically registers in file_registry)
            new_path = self.file_manager.copy_file(
                source_path=file_path,
                dest_filename=filename,
                file_type=file_type,
                description=f"Copy from HPC: {description}"
            )
            
            if new_path:
                # Update state paths for known file types
                if file_type == "trajectory":
                    state["trajectory_path"] = new_path
                    logger.info(f"Updated trajectory_path to: {new_path}")
                elif file_type == "topology":
                    state["topology"] = new_path
                    logger.info(f"Updated topology to: {new_path}")
                
                logger.info(f"Copied {filename} ({file_type}) from HPC to analysis")
                log_file_operation("analysis", "copied", new_path, True, f"From HPC: {description}")

    def _format_pdb_info_for_llm(self, state: MDState) -> str:
        """Format PDB structural information from supervisor for LLM prompts.
        
        Args:
            state: Current MDState with pdb_analysis from supervisor
            
        Returns:
            Formatted string with PDB structural context for LLM
        """
        if not state:
            return ""
        
        pdb_analysis = state.get("pdb_analysis")
        if not pdb_analysis:
            return ""
        
        try:
            total_atoms = pdb_analysis.get("total_atoms", 0)
            total_residues = pdb_analysis.get("total_residues", 0)
            components = pdb_analysis.get("components_available", [])
            summary = pdb_analysis.get("human_readable_summary", "N/A")
            
            # Get protein chain information
            protein_info = pdb_analysis.get("protein", {})
            protein_chains_str = ""
            if protein_info:
                chains_list = []
                for chain_id, chain_data in protein_info.items():
                    if isinstance(chain_data, dict):
                        res_count = chain_data.get("residue_count", 0)
                        chains_list.append(f"Chain {chain_id} ({res_count} residues)")
                if chains_list:
                    protein_chains_str = ", ".join(chains_list)
            
            return f"""
**PDB Structure Information (from supervisor validation):**
- Total Atoms: {total_atoms}
- Total Residues: {total_residues}
- Components: {', '.join(components) if components else 'None'}
- Protein Chains: {protein_chains_str if protein_chains_str else 'None'}
- Summary: {summary}
"""
        except Exception as e:
            logger.warning(f"Failed to format PDB info for LLM: {e}")
            return ""

    def _wrap_trajectory_pbc(self, state: MDState, analysis_dir: str) -> None:
        """
        Wrap the trajectory to fix periodic boundary condition (PBC) artefacts.

        Calls ``wrap_trajectory`` (gmx trjconv -pbc mol -center) and updates
        ``state["trajectory_path"]`` with the wrapped output file so all
        downstream tools use the corrected trajectory.

        Skipped when:
          - ``state["skip_pbc_wrap"]`` is True (caller opted out), or
          - no trajectory file is available, or
          - no TPR file is available (wrapping requires the run-input file), or
          - a valid wrapped trajectory (``mdWrap.xtc``) already exists and is
            not older than the source trajectory (idempotent re-runs).

        Re-wrapping is expensive (CPU/IO/memory), so repeated analysis
        iterations reuse the existing ``mdWrap.xtc`` instead of regenerating it.
        Set ``state["force_pbc_wrap"]=True`` to force a fresh wrap.

        The ligand name is taken from ``state["ligand_resnames"]`` (first entry)
        or falls back to ``"LIG"``.  The output dt (ps) can be overridden via
        ``state["wrap_dt_ps"]`` (default 100 ps).
        """
        if state.get("skip_pbc_wrap"):
            logger.info("_wrap_trajectory_pbc: skip_pbc_wrap=True — skipping")
            return

        # Resolve trajectory
        traj = state.get("trajectory_path")
        if not traj or not Path(traj).exists():
            logger.info("_wrap_trajectory_pbc: no trajectory available — skipping")
            return

        # ── Reuse an already-wrapped trajectory (idempotent re-runs) ───────
        # Wrapping is CPU/IO/memory intensive; avoid repeating it when the
        # user re-iterates analysis. Set state["force_pbc_wrap"]=True to force.
        wrapped_name = "mdWrap.xtc"
        hpc_dir = state.get("hpc_dir") or str(
            Path(state.get("working_directory", "working_dir")) / "hpc"
        )

        if not state.get("force_pbc_wrap"):
            # Case 1: current trajectory already points to the wrapped file.
            if Path(traj).name == wrapped_name and Path(traj).stat().st_size > 0:
                logger.info(
                    "_wrap_trajectory_pbc: trajectory already wrapped "
                    f"({Path(traj).name}) — reusing, skipping re-wrap"
                )
                return

            # Case 2: a wrapped file already exists next to the raw trajectory
            # or in hpc_dir, and is newer than the source — reuse it.
            existing = self._find_existing_wrapped_traj(
                hpc_dir, Path(traj), wrapped_name
            )
            if existing:
                state["trajectory_path"] = existing
                logger.info(
                    "_wrap_trajectory_pbc: found existing wrapped trajectory "
                    f"→ {existing} — reusing, skipping re-wrap"
                )
                return

        # Resolve TPR (required for gmx trjconv -s)
        tpr = (
            state.get("tpr_file")
            or state.get("hpc_dir") and self._find_tpr(state.get("hpc_dir", ""))
            or self._find_tpr(state.get("working_directory", ""))
        )
        if not tpr or not Path(tpr).exists():
            logger.warning(
                "_wrap_trajectory_pbc: no TPR file found — cannot wrap trajectory. "
                "Set state['tpr_file'] or place md.tpr in the hpc/ directory."
            )
            return

        # Ligand name
        ligand_resnames = state.get("ligand_resnames") or []
        ligand = ligand_resnames[0] if ligand_resnames else "LIG"

        # Output dt
        dt = int(state.get("wrap_dt_ps", 100))

        logger.info(
            f"_wrap_trajectory_pbc: wrapping {Path(traj).name} "
            f"(ligand={ligand}, dt={dt} ps) …"
        )

        from src.analysis.trajectory_wrapper import _wrap_trajectory_impl

        # Save wrapped trajectory into hpc_dir (resolved above) so it lives
        # alongside the original simulation data and the reporter can find it.
        result = _wrap_trajectory_impl(
            tpr_file=str(tpr),
            trajectory_file=str(traj),
            output_file=wrapped_name,
            ligand=ligand,
            dt=dt,
            working_dir=hpc_dir,
            skip=False,
        )

        if result.get("success"):
            wrapped = result["wrapped_trajectory"]
            state["trajectory_path"] = wrapped
            logger.info(f"_wrap_trajectory_pbc: trajectory updated → {wrapped}")
        else:
            logger.warning(
                f"_wrap_trajectory_pbc: wrapping failed — continuing with "
                f"original trajectory. Error: {result.get('error', 'unknown')}"
            )

    def _find_existing_wrapped_traj(
        self, hpc_dir: str, source_traj: Path, wrapped_name: str
    ) -> Optional[str]:
        """Locate a previously wrapped trajectory that is safe to reuse.

        Returns the absolute path to an existing, non-empty wrapped trajectory
        that is at least as new as *source_traj* (so stale wraps are ignored).
        Searches hpc_dir, the source trajectory's own directory, and hpc_dir's
        sub-directories. Returns None when no valid wrapped file is found.
        """
        try:
            src_mtime = source_traj.stat().st_mtime if source_traj.exists() else 0.0
        except OSError:
            src_mtime = 0.0

        candidates: List[Path] = []
        if hpc_dir:
            candidates.append(Path(hpc_dir) / wrapped_name)
        candidates.append(source_traj.parent / wrapped_name)

        # Also scan hpc_dir sub-directories (e.g. nested output folders).
        if hpc_dir and Path(hpc_dir).is_dir():
            candidates.extend(sorted(Path(hpc_dir).rglob(wrapped_name)))

        seen: set = set()
        for cand in candidates:
            try:
                resolved = cand.resolve()
            except OSError:
                continue
            if resolved in seen:
                continue
            seen.add(resolved)
            if resolved == source_traj.resolve():
                continue
            if not resolved.is_file() or resolved.stat().st_size == 0:
                continue
            # Ignore wrapped files older than the source (source was re-run).
            if resolved.stat().st_mtime + 1 < src_mtime:
                logger.info(
                    f"_wrap_trajectory_pbc: ignoring stale wrapped file {resolved} "
                    "(older than source trajectory)"
                )
                continue
            return str(resolved)
        return None

    def _find_tpr(self, directory: str) -> Optional[str]:
        """Return the first .tpr file found in *directory* or its sub-dirs."""
        if not directory:
            return None
        for candidate in Path(directory).rglob("*.tpr"):
            return str(candidate.resolve())
        return None

    def _write_pdb_info_to_summary(self, state: MDState, analysis_dir: str) -> None:
        """
        Write PDB validation info from supervisor to analysis summary file.
        This provides context about the input structure for LLM and users.
        
        Args:
            state: Workflow state containing pdb_analysis from supervisor
            analysis_dir: Analysis working directory
        """
        from src.analysis.summary_logger import append_analysis_summary
        
        # Get PDB analysis from state (populated by supervisor's input validation)
        pdb_analysis = state.get("pdb_analysis")
        
        if not pdb_analysis:
            logger.info("No PDB analysis info available from supervisor, skipping summary entry")
            return
        
        try:
            # Extract key information for summary
            total_atoms = pdb_analysis.get("total_atoms", 0)
            total_residues = pdb_analysis.get("total_residues", 0)
            components = pdb_analysis.get("components_available", {})
            summary = pdb_analysis.get("human_readable_summary", "N/A")
            
            # Get topology file path
            topology_file = state.get("topology") or state.get("cleaned_pdb") or state.get("raw_pdb")
            
            # Extract protein sequences if available
            protein_sequences = {}
            if pdb_analysis.get("protein", {}).get("present"):
                chains_info = pdb_analysis.get("protein", {}).get("chains", {})
                for chain_id, chain_data in chains_info.items():
                    sequence = chain_data.get("sequence", "")
                    if sequence:
                        protein_sequences[chain_id] = sequence
            
            # Write to summary file
            append_analysis_summary(
                working_dir=analysis_dir,
                analysis_type="PDB_Input_Validation",
                statistics={
                    "total_atoms": total_atoms,
                    "total_residues": total_residues
                },
                files={
                    "topology_file": topology_file or "N/A"
                },
                metadata={
                    "components_available": components,
                    "human_readable_summary": summary,
                    "protein_sequences": protein_sequences,
                    "source": "supervisor_validation"
                }
            )
            
            logger.info(f"PDB validation summary written: {summary}")
            log_agent_action(
                "analysis",
                "Recorded PDB Structure Info",
                {
                    "atoms": total_atoms,
                    "residues": total_residues,
                    "components": components,
                    "summary": summary
                }
            )
            
        except Exception as e:
            logger.warning(f"Failed to write PDB info to summary: {e}")
            import traceback
            logger.debug(traceback.format_exc())

    def _prepare_agent_input(self, state: MDState) -> AnalysisAgentInput:
        """Prepare structured input for analysis from workflow state"""
        defaults = self.config
        
        # Check if planner provided detailed instructions for this agent
        # Prefer pre-extracted instructions from supervisor
        planner_instructions = state.get("analysis_instructions")
        
        if not planner_instructions:
            # Fallback: Extract from execution_plan if supervisor didn't provide it
            execution_plan = state.get("execution_plan", {})
            if execution_plan.get("format") == "natural_language":
                full_plan = execution_plan.get("full_plan", "")
                planner_instructions = self._extract_agent_instructions(full_plan, "Analysis Agent")
        
        # Append human recommendation so the LLM sees it
        human_rec = state.get("human_recommendation")
        if human_rec:
            rec_block = (
                f"\n\n**HUMAN RECOMMENDATION (must be followed):**\n{human_rec}\n"
                "Adjust the analysis plan to incorporate this recommendation."
            )
            if planner_instructions:
                planner_instructions += rec_block
            else:
                planner_instructions = rec_block
        
        # Resolve topology path: prefer the hpc_dir copy over the simsetup
        # original so the analysis agent always sees files from the same
        # directory tree as the trajectory/energy outputs.
        topology_file = state.get("topology")
        hpc_dir = state.get("hpc_dir") or state.get("hpc_output_directory") or state.get("hpc_directory")
        if hpc_dir:
            hpc_dir_path = Path(hpc_dir)
            # Check for topology files in hpc_dir by priority: .top > .tpr
            for candidate_name in (
                Path(topology_file).name if topology_file else None,
                "topol.top",
                "topology.top",
            ):
                if candidate_name:
                    candidate = hpc_dir_path / candidate_name
                    if candidate.exists():
                        topology_file = str(candidate)
                        logger.info(f"analysis: resolved topology to hpc copy: {topology_file}")
                        break
            # Also check results sub-directory (download_results destination)
            if not (topology_file and Path(topology_file).exists()):
                for candidate_name in ("topol.top", "topology.top"):
                    candidate = hpc_dir_path / "results" / candidate_name
                    if candidate.exists():
                        topology_file = str(candidate)
                        logger.info(f"analysis: resolved topology from hpc/results: {topology_file}")
                        break

        return AnalysisAgentInput(
            working_directory=state.get("working_directory", "working_dir"),
            hpc_output_dir=state.get("hpc_output_directory", ""),
            topology_file=topology_file,
            trajectory_file=state.get("trajectory_path"),
            energy_file=state.get("energy_file"),
            analyses=defaults.get("metrics", ["rmsd", "rmsf", "gyration"]),
            user_goal=state.get("user_goal", ""),
            enriched_goal=state.get("enriched_prompt") or state.get("rephrased_goal"),
            additional_instructions=planner_instructions
        )

    def _run_analysis_workflow(self, agent_input: AnalysisAgentInput, 
                               state: MDState) -> AnalysisAgentOutput:
        """
        Run complete analysis workflow:
        1. LLM creates intelligent plan based on available data
        2. Execute plan step-by-step using tools
        3. Return structured results
        """
        try:
            # Step 1: LLM analyzes available data and creates plan.
            # When human_recommendation is set, replan on top of the existing plan
            # so the recommendation is actually applied (not bypassed).
            exec_plan = state.get("execution_plan")
            human_rec = state.get("human_recommendation")
            if human_rec:
                logger.info("analysis: replanning with human guidance: %s", human_rec[:120])
                _updated = self.replan_with_guidance(human_rec, state)
                if _updated:
                    plan = AnalysisPlan(
                        reasoning=_updated.get("reasoning", ""),
                        overview=_updated.get("overview", ""),
                        steps=[
                            AnalysisStep(
                                name=s.get("name", ""),
                                description=s.get("description", ""),
                                tool_name=s.get("tool_name", ""),
                                tool_params=s.get("tool_params", {}),
                                reason=s.get("reason", "")
                            )
                            for s in _updated.get("steps", [])
                        ],
                        potential_issues=_updated.get("potential_issues", []),
                        recommendations=_updated.get("recommendations", []),
                    )
                else:
                    # LLM unavailable — fall back; human_rec is already in additional_instructions
                    plan = self._create_analysis_plan_llm(agent_input, state)
            else:
                plan = self._create_analysis_plan_llm(agent_input, state)

            log_agent_action("analysis", "Generated analysis plan", {
                "steps": len(plan.steps),
                "tools": [s.tool_name for s in plan.steps],
                "reasoning": plan.reasoning,
            })

            # Persist structured plan to state for HITL inspection/modification
            if exec_plan is not None:
                exec_plan.setdefault("structured_plans", {})["analysis"] = plan.model_dump()
            
            # Step 2: Execute plan using tool executor
            result = self._execute_analysis_plan(agent_input, plan, state)
            
            # Step 3: Register created files in file_registry
            file_registry = state.get("file_registry", {})
            
            for file_path, description in result.generated_files.items():
                # Determine file type from extension
                file_type = "analysis_output"
                if ".dat" in file_path or ".xvg" in file_path:
                    file_type = "analysis_data"
                elif ".png" in file_path or ".pdf" in file_path:
                    file_type = "plot"
                
                file_registry[file_path] = {
                    "type": file_type,
                    "description": description,
                    "stage": "analysis"
                }
            
            # Write back modified file_registry to state
            state["file_registry"] = file_registry
            
            # Step 4: Prepare supervisor update
            supervisor_update = {
                "analysis_results": result.results,
                "analysis_directory": result.output_directory,
                "analysis_report": result.report,
                "file_registry": file_registry
            }
            
            return AnalysisAgentOutput(
                success=result.success,
                plan=plan,
                result=result,
                supervisor_update=supervisor_update
            )
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Analysis workflow failed: {e}")
            logger.error(f"Traceback: {tb}")
            return AnalysisAgentOutput(
                success=False,
                plan=AnalysisPlan(
                    reasoning=f"Error in planning: {str(e)}",
                    overview="Failed",
                    steps=[]
                ),
                result=AnalysisExecutionResult(
                    success=False,
                    report=f"Error: {str(e)}\n\nTraceback:\n{tb}",
                    issues=[str(e)],
                    warnings=[],
                    output_directory=state.get("analysis_directory", "./working_dir/analysis")
                ),
                supervisor_update={}
            )

    def _update_state(self, state: MDState, agent_output: AnalysisAgentOutput):
        """Update workflow state with analysis results"""
        if agent_output.supervisor_update:
            state.update(agent_output.supervisor_update)
        
        state["analysis_report"] = agent_output.result.report
        state["analysis_issues"] = agent_output.result.issues
        state["analysis_warnings"] = agent_output.result.warnings
        state["analysis_execution_log"] = agent_output.result.execution_log
        
        # Initialize file registry if not present
        if "file_registry" not in state or state["file_registry"] is None:
            state["file_registry"] = {}
        
        # Register all generated files with metadata
        for file_path, description in agent_output.result.generated_files.items():
            # Determine file type from filename
            file_type = "analysis_output"
            if ".dat" in file_path or ".xvg" in file_path:
                file_type = "analysis_data"
            elif ".png" in file_path or ".pdf" in file_path:
                file_type = "plot"
            
            state["file_registry"][file_path] = {
                "type": file_type,
                "description": description,
                "stage": "analysis"
            }

    def _llm_plan_json_with_retry(
        self,
        prompt: str,
        log_label: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 16384,
    ) -> Dict[str, Any]:
        """Call the LLM for a JSON plan; retry once when the response has no steps.

        Reasoning models occasionally return empty content (reasoning-only) or a
        JSON object without a ``steps`` array. A single strict retry recovers most
        of these before the caller falls back to the deterministic template.
        """
        content = self.llm.prompt_raw(
            prompt, temperature=temperature, max_tokens=max_tokens, format="json"
        )
        log_llm_interaction(
            log_label, prompt, content,
            is_mock=hasattr(self.llm, "_is_mock_mode") and self.llm._is_mock_mode,
        )
        plan_dict = self._extract_plan_json(content)

        if not (content or "").strip() or not plan_dict.get("steps"):
            logger.warning(
                "%s: empty/invalid JSON plan (content=%d chars, steps=%d); retrying once",
                log_label, len((content or "").strip()),
                len(plan_dict.get("steps", []) or []),
            )
            retry_prompt = (
                prompt
                + "\n\nIMPORTANT: Your previous reply was empty or missing the "
                "\"steps\" array. Reply with ONLY a single valid JSON object of the "
                "form {\"reasoning\":..., \"overview\":..., \"steps\":[{...}], "
                "\"potential_issues\":[], \"recommendations\":[]}. Every requested "
                "metric must appear as a step. No prose, no markdown fences."
            )
            content = self.llm.prompt_raw(
                retry_prompt, temperature=0.0, max_tokens=max(max_tokens, 24576), format="json"
            )
            log_llm_interaction(
                f"{log_label}.retry", retry_prompt, content,
                is_mock=hasattr(self.llm, "_is_mock_mode") and self.llm._is_mock_mode,
            )
            plan_dict = self._extract_plan_json(content)

        plan_dict["_raw_content"] = content
        return plan_dict

    def _create_analysis_plan_llm(self, agent_input: AnalysisAgentInput, state: MDState) -> AnalysisPlan:
        """
        Use LLM to analyze available data and create intelligent analysis plan.
        Falls back to template-based plan if LLM fails.
        """
        # Build LLM prompt from config template
        prompt = self._build_analysis_planning_prompt(agent_input, state)
        
        try:
            plan_dict = self._llm_plan_json_with_retry(
                prompt, "analysis.planning", temperature=0.2, max_tokens=16384
            )
            content = plan_dict.pop("_raw_content", "")
            plan_dict = self._normalize_plan_steps(plan_dict, agent_input)

            llm_step_count = len(plan_dict.get("steps", []))
            llm_reasoning = plan_dict.get("reasoning", "")

            plan_dict = self._filter_plan_steps_by_intent(plan_dict, state, agent_input)

            # Post-process: inject mandatory steps the LLM may have omitted
            plan_dict = self._inject_mandatory_steps(plan_dict, agent_input, state)
            plan_dict = self._ensure_requested_metric_steps(plan_dict, agent_input, state)
            plan_dict = self._filter_plan_steps_by_intent(plan_dict, state, agent_input)

            final_step_count = len(plan_dict.get("steps", []))
            if final_step_count > llm_step_count:
                tools = [s.get("tool_name", "") for s in plan_dict.get("steps", [])]
                plan_dict["reasoning"] = (
                    f"Expanded LLM draft ({llm_step_count} steps) to {final_step_count} steps "
                    f"covering all metrics in the enriched user goal. "
                    f"Tools: {', '.join(tools)}."
                )
            elif not plan_dict.get("reasoning"):
                plan_dict["reasoning"] = llm_reasoning or content[:500]

            return AnalysisPlan(
                reasoning=plan_dict.get("reasoning", content[:500]),
                overview=plan_dict.get("overview", "Analyzing MD trajectory"),
                steps=[
                    AnalysisStep(
                        name=step.get("name", "unknown"),
                        description=step.get("description", ""),
                        tool_name=step.get("tool_name", ""),
                        tool_params=step.get("tool_params", {}),
                        reason=step.get("reason", "")
                    )
                    for step in plan_dict.get("steps", [])
                ],
                potential_issues=plan_dict.get("potential_issues", []),
                recommendations=plan_dict.get("recommendations", [])
            )
            
        except Exception as e:
            logger.warning(f"LLM planning failed, using fallback: {e}")
            return self._create_fallback_analysis_plan(agent_input, state)

    def _intent_metrics(
        self,
        state: MDState,
        agent_input: Optional[AnalysisAgentInput] = None,
    ) -> Optional[FrozenSet[str]]:
        """Requested metrics for the current simulation (per-sim goal takes precedence)."""
        base = detect_requested_metrics_for_sim(state, agent_input)
        enriched = self._resolve_enriched_goal_for_planning(state, agent_input)
        if not enriched:
            return base
        extra = detect_requested_metrics(enriched)
        if base is None and extra is None:
            return None
        merged = set(base or ()) | set(extra or ())
        return frozenset(merged) if merged else None

    def _sims_for_combined_metric(
        self,
        state: MDState,
        sim_dirs: List[str],
        labels: List[str],
        metric: str,
        label_name_map: Optional[Dict[str, str]] = None,
    ) -> tuple[List[str], List[str]]:
        """Simulations that should participate in one combined metric (may be a subset)."""
        return resolve_sims_for_combined_metric(
            metric,
            sim_dirs,
            labels,
            master_goal=state.get("user_goal_original") or "",
            combined_plan=state.get("combined_analysis_plan") or "",
            completed_sim_states=state.get("completed_sim_states") or [],
            label_name_map=label_name_map,
        )

    def _filter_plan_steps_by_intent(
        self,
        plan_dict: Dict[str, Any],
        state: MDState,
        agent_input: Optional[AnalysisAgentInput] = None,
    ) -> Dict[str, Any]:
        """Remove analysis steps outside the explicit metric scope in user goals."""
        if state.get("hitl_chat_task"):
            return plan_dict

        requested = self._intent_metrics(state, agent_input)
        if requested is None:
            return plan_dict

        allowed_data_files = {
            STANDARD_OUTPUT_FILES[m]["data"]
            for m in requested
            if m in STANDARD_OUTPUT_FILES and "data" in STANDARD_OUTPUT_FILES[m]
        }
        allowed_plot_files = {
            STANDARD_OUTPUT_FILES[m]["plot"]
            for m in requested
            if m in STANDARD_OUTPUT_FILES and "plot" in STANDARD_OUTPUT_FILES[m]
        }

        filtered: List[Dict[str, Any]] = []
        for step in plan_dict.get("steps", []):
            tool = step.get("tool_name", "")
            if tool in _PREP_TOOLS:
                continue
            metric = _CALC_TOOL_TO_METRIC.get(tool)
            if metric is not None:
                if metric in requested:
                    filtered.append(step)
                continue
            if tool in {"plot_md_data", "plot_multipanel", "plot_md_multipanel"}:
                params = step.get("tool_params") or {}
                data_files = params.get("data_files") or []
                out_file = str(params.get("output_file", ""))
                data_ok = any(
                    df in allowed_data_files
                    or any(m in str(df).lower() for m in requested)
                    for df in data_files
                )
                plot_ok = out_file in allowed_plot_files or not out_file
                if data_ok and plot_ok:
                    filtered.append(step)
                continue
            filtered.append(step)

        if filtered:
            plan_dict["steps"] = filtered
        plan_dict = self._dedupe_com_distance_steps(plan_dict, state, agent_input)
        return plan_dict

    def _dedupe_com_distance_steps(
        self,
        plan_dict: Dict[str, Any],
        state: MDState,
        agent_input: Optional[AnalysisAgentInput] = None,
    ) -> Dict[str, Any]:
        """Keep one COM-distance tool unless the user explicitly requested both."""
        goal = " ".join(collect_goal_texts_for_intent(state, agent_input))
        mode = detect_com_distance_mode(goal)
        if mode == "both":
            return plan_dict
        drop = "calculate_com_distance" if mode == "pocket" else "calculate_ligand_pocket_distance"
        steps = [
            s for s in plan_dict.get("steps", [])
            if s.get("tool_name") != drop
        ]
        if len(steps) != len(plan_dict.get("steps", [])):
            logger.info(
                "_dedupe_com_distance_steps: removed %s (COM mode=%s)",
                drop, mode,
            )
        plan_dict["steps"] = steps
        return plan_dict

    def _detect_ligand_resname(self, agent_input: AnalysisAgentInput, state: MDState) -> str:
        """Determine the ligand residue name to use for pocket-distance analysis.

        Priority:
        1. state["ligand_resnames"] (set by supervisor input validation)
        2. pdb_analysis["ligand"]["residue_names"] (from supervisor structure inspection)
        3. Known ligand names found in user_goal text
        4. Regex pattern "resname XYZ" in user_goal
        5. Default "LIG"
        """
        # 1. Explicit state field set by supervisor
        ligand_resnames = state.get("ligand_resnames") or []
        if ligand_resnames:
            return ligand_resnames[0]

        # 2. pdb_analysis from input validation
        pdb_analysis = state.get("pdb_analysis") or {}
        ligand_info = pdb_analysis.get("ligand", {})
        if isinstance(ligand_info, dict):
            residue_names = ligand_info.get("residue_names", [])
            if residue_names:
                return residue_names[0]

        # 3 & 4. Parse user goal text
        user_goal = (
            state.get("user_goal_original") or
            state.get("user_goal") or
            agent_input.user_goal or
            ""
        )
        known_ligands = ["ATP", "ADP", "AMP", "GTP", "GDP", "NAD", "FAD", "FMN", "LIG", "INH"]
        for lig in known_ligands:
            if lig in user_goal.upper():
                return lig
        match = re.search(r'\bresname\s+([A-Z0-9]{1,5})\b', user_goal, re.IGNORECASE)
        if match:
            return match.group(1).upper()

        return "LIG"

    def _is_holo_simulation(self, state: MDState, agent_input: AnalysisAgentInput) -> bool:
        """True when the current per-simulation run is a ligand-bound (holo) system."""
        from src.analysis.combined_analysis import is_holo_simulation

        label = ""
        sim_prompts = state.get("sim_prompts") or []
        idx = state.get("current_sim_index")
        if idx is not None and 0 <= idx < len(sim_prompts):
            label = sim_prompts[idx].get("label", "")
        if not label:
            label = Path(state.get("working_directory", "")).name
        sim_dir = state.get("working_directory", "")
        if is_holo_simulation(sim_dir, label):
            return True

        goal_text = " ".join(
            t for t in (
                state.get("user_goal"),
                state.get("user_goal_original"),
                getattr(agent_input, "user_goal", None),
            )
            if t
        ).lower()
        if any(kw in goal_text for kw in ("holo", "protein–atp", "protein-atp", "atp", "ligand")):
            return True

        requested = self._intent_metrics(state, agent_input)
        binding_metrics = frozenset({
            "com", "contacts", "pocket_sasa", "residence", "pocket_rmsf", "ligand_rmsf",
        })
        if requested and requested & binding_metrics:
            return True
        return False

    @staticmethod
    def _analysis_step_to_dict(step: AnalysisStep) -> Dict[str, Any]:
        return {
            "name": step.name,
            "description": step.description,
            "tool_name": step.tool_name,
            "tool_params": step.tool_params,
            "reason": step.reason,
        }

    def _ensure_requested_metric_steps(
        self,
        plan_dict: Dict[str, Any],
        agent_input: AnalysisAgentInput,
        state: MDState,
    ) -> Dict[str, Any]:
        """Merge fallback steps for requested metrics missing from the LLM plan."""
        if state.get("hitl_chat_task"):
            return plan_dict

        requested = self._intent_metrics(state, agent_input)
        if not requested:
            return plan_dict

        existing_tools = {s.get("tool_name", "") for s in plan_dict.get("steps", [])}
        missing_metrics: Set[str] = set()
        binding_rmsf = (requested or frozenset()) & {"pocket_rmsf", "ligand_rmsf"}
        for metric in requested:
            if metric == "rmsf" and binding_rmsf:
                covered = all(
                    any(
                        _CALC_TOOL_TO_METRIC.get(tool) == binding_metric
                        for tool in existing_tools
                    )
                    for binding_metric in binding_rmsf
                )
                if covered:
                    continue
            if not any(
                _CALC_TOOL_TO_METRIC.get(tool) == metric for tool in existing_tools
            ):
                missing_metrics.add(metric)

        if "fel" in missing_metrics:
            missing_metrics.add("pca")

        if not missing_metrics:
            return plan_dict

        fallback = self._create_fallback_analysis_plan(agent_input, state)
        merged = list(plan_dict.get("steps", []))
        merged_outputs = {
            str(s.get("tool_params", {}).get("output_file", ""))
            for s in merged
        }

        for fb_step in fallback.steps:
            tool = fb_step.tool_name
            metric = _CALC_TOOL_TO_METRIC.get(tool)
            if metric and metric in missing_metrics and tool not in existing_tools:
                merged.append(self._analysis_step_to_dict(fb_step))
                existing_tools.add(tool)
                out = str(fb_step.tool_params.get("output_file", ""))
                if out:
                    merged_outputs.add(out)
                continue

            if tool in {"plot_md_data", "plot_pca_projection", "plot_multipanel"}:
                out_file = str(fb_step.tool_params.get("output_file", ""))
                if out_file and out_file in merged_outputs:
                    continue
                data_files = fb_step.tool_params.get("data_files") or []
                for m in missing_metrics:
                    spec = STANDARD_OUTPUT_FILES.get(m, {})
                    plot_ok = out_file and out_file == spec.get("plot")
                    data_ok = any(df == spec.get("data") for df in data_files)
                    if plot_ok or data_ok:
                        merged.append(self._analysis_step_to_dict(fb_step))
                        if out_file:
                            merged_outputs.add(out_file)
                        break

        if len(merged) > len(plan_dict.get("steps", [])):
            logger.info(
                "_ensure_requested_metric_steps: added steps for missing metrics: %s",
                sorted(missing_metrics),
            )
            plan_dict["steps"] = merged
        return plan_dict

    def _inject_mandatory_steps(self, plan_dict: Dict[str, Any],
                                 agent_input: AnalysisAgentInput,
                                 state: MDState) -> Dict[str, Any]:
        """Post-process the LLM plan to inject mandatory steps that the LLM may have omitted."""
        if state.get("hitl_chat_task"):
            return plan_dict

        steps = plan_dict.get("steps", [])
        requested = self._intent_metrics(state, agent_input)
        narrow_scope = requested is not None

        # --- Ligand pocket distance / protein–ligand COM ---
        existing_tools = {s.get("tool_name", "") for s in steps}
        user_goal_lower = (
            state.get("user_goal")
            or state.get("user_goal_original")
            or agent_input.user_goal
            or ""
        ).lower()
        com_mode = detect_com_distance_mode(user_goal_lower)
        narrow_com = narrow_scope and "com" not in (requested or frozenset())

        if "calculate_ligand_pocket_distance" not in existing_tools:
            ligand_keywords = [
                "ligand", "atp", "adp", "amp", "gtp", "gdp", "nad",
                "inhibitor", "pocket", "binding site", "catalytic pocket",
                "catalytic site", "active site",
            ]
            needs_pocket_distance = com_mode in ("pocket", "both") and any(
                kw in user_goal_lower for kw in ligand_keywords
            )

            if narrow_com:
                needs_pocket_distance = False

            # Also trigger if pdb_analysis shows a ligand is present (broad scope only)
            if not needs_pocket_distance and not narrow_scope and com_mode != "protein_com":
                pdb_analysis = state.get("pdb_analysis") or {}
                ligand_info = pdb_analysis.get("ligand", {})
                if isinstance(ligand_info, dict) and ligand_info.get("present"):
                    needs_pocket_distance = True

            if needs_pocket_distance and not self._is_holo_simulation(state, agent_input):
                logger.info(
                    "_inject_mandatory_steps: skipping ligand pocket distance — "
                    "protein-only (apo) simulation has no bound ligand"
                )
                needs_pocket_distance = False

            if needs_pocket_distance:
                ligand_resname = self._detect_ligand_resname(agent_input, state)
                topo_file = (
                    Path(agent_input.topology_file).name
                    if agent_input.topology_file else "md.gro"
                )
                traj_file = (
                    Path(agent_input.trajectory_file).name
                    if agent_input.trajectory_file else "md.xtc"
                )
                pocket_step = {
                    "name": "Calculate Ligand Pocket COM Distance",
                    "description": (
                        f"Identify protein pocket atoms within 5 Å of {ligand_resname} "
                        "at frame 0, then track COM-to-COM distance over the trajectory."
                    ),
                    "tool_name": "calculate_ligand_pocket_distance",
                    "tool_params": {
                        "topology_file": topo_file,
                        "trajectory_file": traj_file,
                        "ligand_selection": f"resname {ligand_resname.upper()}",
                        "cutoff": 5.0,
                        "output_file": "ligand_pocket_distance.csv",
                    },
                    "reason": "User requested COM distance between the ligand and the catalytic pocket.",
                }
                pocket_plot_step = {
                    "name": "Plot Ligand Pocket COM Distance",
                    "description": "Plot the ligand-to-pocket COM distance over simulation time.",
                    "tool_name": "plot_md_data",
                    "tool_params": {
                        "data_files": ["ligand_pocket_distance.csv"],
                        "output_file": "ligand_pocket_distance.png",
                        "x_col": 1,
                        "y_col": 2,
                        "xlabel": "Time (ns)",
                        "ylabel": "COM Distance (Å)",
                        "titles": f"Ligand ({ligand_resname.upper()}) — Catalytic Pocket COM Distance",
                    },
                    "reason": "Mandatory plot after calculate_ligand_pocket_distance.",
                }
                steps.extend([pocket_step, pocket_plot_step])
                plan_dict["steps"] = steps
                logger.info(
                    "_inject_mandatory_steps: injected calculate_ligand_pocket_distance "
                    f"(ligand_selection='resname {ligand_resname.upper()}') — "
                    f"COM mode={com_mode}"
                )

        # --- Whole-protein COM distance (explicit selection1/selection2) ---
        existing_tools = {s.get("tool_name", "") for s in steps}
        if (
            "calculate_com_distance" not in existing_tools
            and com_mode in ("protein_com", "both")
            and not narrow_com
        ):
            ligand_resname = self._detect_ligand_resname(agent_input, state)
            topo_file = (
                Path(agent_input.topology_file).name
                if agent_input.topology_file else "md.gro"
            )
            traj_file = (
                Path(agent_input.trajectory_file).name
                if agent_input.trajectory_file else "md.xtc"
            )
            com_step = {
                "name": "Calculate Protein–Ligand COM Distance",
                "description": (
                    f"Per-frame COM distance between the whole protein and "
                    f"{ligand_resname.upper()}."
                ),
                "tool_name": "calculate_com_distance",
                "tool_params": {
                    "topology_file": topo_file,
                    "trajectory_file": traj_file,
                    "selection1": "protein",
                    "selection2": f"resname {ligand_resname.upper()}",
                    "label1": "Protein",
                    "label2": ligand_resname.upper(),
                    "output_file": "com_distance.csv",
                },
                "reason": "User requested whole-protein COM distance to the ligand.",
            }
            com_plot_step = {
                "name": "Plot Protein–Ligand COM Distance",
                "description": "Plot protein-to-ligand COM distance over time.",
                "tool_name": "plot_md_data",
                "tool_params": {
                    "data_files": ["com_distance.csv"],
                    "output_file": "com_distance.png",
                    "x_col": 1,
                    "y_col": 2,
                    "xlabel": "Time (ns)",
                    "ylabel": "COM Distance (Å)",
                    "titles": f"Protein — {ligand_resname.upper()} COM Distance",
                },
                "reason": "Mandatory plot after calculate_com_distance.",
            }
            if self._is_holo_simulation(state, agent_input):
                steps.extend([com_step, com_plot_step])
                plan_dict["steps"] = steps
                logger.info(
                    "_inject_mandatory_steps: injected calculate_com_distance — "
                    f"COM mode={com_mode}"
                )

        # --- DCCM --- only when the per-simulation goal explicitly requests it
        if "calculate_dccm" not in existing_tools:
            needs_dccm = requested is not None and "dccm" in requested

            if needs_dccm:
                topo_file = (
                    Path(agent_input.topology_file).name
                    if agent_input.topology_file else "md.gro"
                )
                traj_file = (
                    Path(agent_input.trajectory_file).name
                    if agent_input.trajectory_file else "md.xtc"
                )
                dccm_step = {
                    "name": "Calculate Dynamic Cross-Correlation Matrix (DCCM)",
                    "description": (
                        "Compute normalised DCCM of Cα fluctuations to reveal "
                        "correlated and anti-correlated residue motions. "
                        "Generates dccm.csv and dccm_heatmap.png internally."
                    ),
                    "tool_name": "calculate_dccm",
                    "tool_params": {
                        "topology_file": topo_file,
                        "trajectory_file": traj_file,
                        "selection": "protein and name CA",
                        "output_prefix": "dccm",
                        "frame_interval": 5,
                        "save_matrix_csv": True,
                        "create_heatmap": True,
                    },
                    "reason": (
                        "User goal mentions correlated motions / DCCM / pseudokinase "
                        "dynamics — DCCM reveals allosteric communication patterns."
                    ),
                }
                steps.append(dccm_step)
                plan_dict["steps"] = steps
                logger.info(
                    "_inject_mandatory_steps: injected calculate_dccm — "
                    "triggered by user_goal keywords"
                )

        # --- Combined metrics panel plot ---
        # Always inject plot_multipanel → combined_metrics.png unless the
        # LLM already included a multipanel step.
        _current_tools = {s.get("tool_name", "") for s in steps}
        _MULTIPANEL_TOOLS = {"plot_multipanel", "plot_md_multipanel"}
        if not (_current_tools & _MULTIPANEL_TOOLS):
            # Collect .dat output files from standard metric steps already in the plan
            _DAT_LABEL: Dict[str, tuple] = {
                "rmsd":     ("Time (ns)", "RMSD (Å)", "RMSD"),
                "rmsf":     ("Residue",   "RMSF (Å)", "RMSF"),
                "gyration": ("Time (ns)", "Rg (Å)",   "Radius of Gyration"),
                "rg":       ("Time (ns)", "Rg (Å)",   "Radius of Gyration"),
                "energy":   ("Time (ns)", "Energy (kJ/mol)", "Energy"),
            }
            panel_files: List[str] = []
            xlabels:     List[str] = []
            ylabels:     List[str] = []
            titles:      List[str] = []
            for s in steps:
                out = str(s.get("tool_params", {}).get("output_file", ""))
                if out.endswith(".dat"):
                    fname = Path(out).name
                    for key, (xl, yl, tl) in _DAT_LABEL.items():
                        if key in fname.lower():
                            if fname not in panel_files:
                                panel_files.append(fname)
                                xlabels.append(xl)
                                ylabels.append(yl)
                                titles.append(tl)
                            break
            # Inject multipanel only when ≥2 standard panels and scope is not single-metric
            if narrow_scope and len(requested) < 2:
                panel_files = []
            elif len(panel_files) >= 2:
                multipanel_step = {
                    "name": "Create Combined Metrics Plot",
                    "description": (
                        "Multi-panel summary figure of all standard MD metrics "
                        "(RMSD, RMSF, Rg and optionally energy) in one PNG."
                    ),
                    "tool_name": "plot_multipanel",
                    "tool_params": {
                        "data_files": panel_files,
                        "output_file": "combined_metrics.png",
                        "layout": "vertical",
                        "titles": titles,
                        "xlabels": xlabels,
                        "ylabels": ylabels,
                    },
                    "reason": (
                        "Mandatory combined overview plot — always generated for every "
                        "individual simulation so each simulation folder contains the same "
                        "quality-control figure."
                    ),
                }
                steps.append(multipanel_step)
                plan_dict["steps"] = steps
                logger.info(
                    "_inject_mandatory_steps: injected plot_multipanel → combined_metrics.png "
                    "(%d panels: %s)", len(panel_files), panel_files
                )

        return plan_dict

    def _build_analysis_planning_prompt(self, agent_input: AnalysisAgentInput, 
                                        state: MDState) -> str:
        """Build LLM planning prompt - use planner's detailed instructions if available"""
        
        # Check if we have detailed instructions from planner
        if agent_input.additional_instructions:
            logger.info("Using planner's detailed instructions for analysis")
            return self._build_prompt_from_planner_instructions(
                agent_input, agent_input.additional_instructions, state
            )
        
        # Otherwise use standard config-based prompt
        return self._build_standard_analysis_prompt(agent_input, state)

    def _build_prompt_from_planner_instructions(self, agent_input: AnalysisAgentInput,
                                                planner_instructions: str,
                                                state: MDState) -> str:
        """Build prompt using planner's detailed natural language instructions"""
        
        tool_metadata = self._get_analysis_tool_metadata(state)
        tools_list_str = self._format_tools_list_detailed(tool_metadata)
        scope_note = self._get_per_sim_tool_scope_note(state)
        input_files_block = self._format_trajectory_input_block(agent_input)
        goal_context = self._format_goal_context_for_planning(agent_input, state)

        goal_text = " ".join(collect_goal_texts_for_intent(state, agent_input)).lower()
        _pca_fel_block = (
            get_pca_fel_tool_guide()
            if any(k in goal_text for k in ("pca", "principal component", "free energy landscape", "fel", "energy landscape", "essential dynamics"))
            else ""
        )
        _classification_block = (
            get_classification_per_sim_tool_guide()
            if detect_classification_requested(*collect_goal_texts_for_intent(state, agent_input))
            else ""
        )
        
        # Extract file registry information
        file_registry = state.get("file_registry", {})
        if file_registry:
            registry_str = "\n**Files Available from HPC:**\n"
            for file_path, metadata in file_registry.items():
                if metadata.get("stage") == "hpc":
                    filename = Path(file_path).name
                    file_type = metadata.get("type", "unknown")
                    description = metadata.get("description", "")
                    registry_str += f"- {filename} (type: {file_type}) - {description}\n"
        else:
            registry_str = "\n**Files Available from HPC:** None registered\n"
        
        # Extract PDB structural information from supervisor validation
        pdb_info_str = self._format_pdb_info_for_llm(state)
        
        return f"""You are a molecular dynamics analysis expert executing a detailed plan from the workflow planner.

**Available Data:**
- Topology File: {agent_input.topology_file or "Not available"}
- Trajectory File: {agent_input.trajectory_file or "Not available"}
- Energy File: {agent_input.energy_file or "Not available"}
{goal_context}
{input_files_block}
{registry_str}
{pdb_info_str}

**INTENT (HIGHEST PRIORITY — overrides planner if they conflict):**
The **Enriched User Goal** (when present) is the authoritative per-simulation scope.
Your JSON plan MUST include a calculate_*/analyze_* step plus plot_md_data (or plot_pca_projection)
for **every** metric named in the Enriched User Goal — not just the first one.
Planner instructions below are a reference checklist only: omit any planner step whose metric
is absent from the Enriched User Goal; add every metric the Enriched User Goal requests even
if the planner omits it.
If the Enriched User Goal says "RMSF only" (or similar exclusive language), plan ONLY that metric.

{get_standard_output_filenames_block()}

**DETAILED INSTRUCTIONS FROM PLANNER (guidance only — do not exceed User Goal scope):**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{planner_instructions}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Available Tools:**
{tools_list_str}

{scope_note}
**CRITICAL INSTRUCTIONS:**
- You MUST ONLY use the tools listed above - do NOT invent or suggest non-existent tools
- Every "tool_name" in your plan must match exactly one of the tool names listed above
- FORBIDDEN tool names: "none", "manual", "skip", "custom", "placeholder", or any made-up tool
- For input file parameters (topology_file, trajectory_file, energy_file etc.):
  Use ONLY the exact filenames from **Required input filenames** above.
  NEVER use trajectory.dcd, md.dcd, or invented paths.
- For plot_md_data use **data_files** (list), e.g. `"data_files": ["ligand_pocket_distance.csv"]` — not data_file.
- For plot_pca_projection use **pca_projections_file** (from calculate_trajectory_pca), not pca_file or input_file.
- For calculate_trajectory_pca use **projections_file** / **variance_file**, not output_file.
- For output file parameters (output_file, plot_file, csv_file etc.):
  Use ONLY the file name (e.g. "rmsd.dat"). The framework prepends the output directory.
- If a required capability is missing, either:
  a) Use available tools creatively to achieve the same goal, OR
  b) OMIT that step entirely from your plan (do NOT include it with tool_name="none")
- When you cannot perform a step, simply do NOT include it in the steps array

**MANDATORY PLOTTING RULE — CRITICAL:**
- After EVERY calculate_* or analyze_* step that produces a data file, you MUST immediately
  add a plot_md_data step to visualise that data.
- The plot step's data_files must be ["<output_file_from_previous_step>"] (filename only, no path).
- Example pair:
    {{"tool_name": "calculate_rmsd", "tool_params": {{"output_file": "rmsd.dat", ...}}}},
    {{"tool_name": "plot_md_data",   "tool_params": {{"data_files": ["rmsd.dat"], "output_file": "rmsd.png", "xlabel": "Time (ns)", "ylabel": "RMSD (Å)"}}}}
- Apply this pattern for RMSD, RMSF, Rg, energy, and any distance calculation.
{get_com_distance_tool_guide()}
{_pca_fel_block}
{_classification_block}
- **DCCM — only when the User Goal explicitly names DCCM for this simulation:**
  Include calculate_dccm only if DCCM is requested in the User Goal for this run.
  Do NOT add DCCM because the global project mentions it for other proteins.
  Use: selection="protein and name CA", frame_interval=5, output_prefix="dccm".

Your task: Create a detailed, step-by-step execution plan that implements **every analysis**
in the Enriched User Goal (or User Goal when no enriched text exists). Follow planner
instructions only where they match that scope. When ligand/pocket/COM distance is requested,
include the correct COM tool from the guide above (not both unless both are requested).
The plan should specify which tools to call and in what order.
ONLY include steps that use valid tools from the list above.
Your "steps" array must list ALL requested calculations and plots — a partial plan is invalid.

Output as JSON with this structure (object with "steps", NOT a tool-call array):
{{
  "reasoning": "How you'll implement the planner's instructions",
  "overview": "High-level summary",
  "steps": [
    {{
      "name": "step name",
      "description": "what it does",
      "tool_name": "tool to call",
      "tool_params": {{"topology_file": "{Path(agent_input.topology_file).name if agent_input.topology_file else 'md.tpr'}", "trajectory_file": "{Path(agent_input.trajectory_file).name if agent_input.trajectory_file else 'md.xtc'}", "output_file": "example.dat"}},
      "reason": "why it's needed per planner's instructions"
    }}
  ],
  "potential_issues": ["issue1"],
  "recommendations": ["rec1"]
}}
Return ONLY this JSON object — no markdown fences, no [{{"name":..., "arguments":...}}] array.
"""

    def _build_standard_analysis_prompt(self, agent_input: AnalysisAgentInput, state: MDState = None) -> str:
        """Build LLM planning prompt from config template using dynamic tool metadata"""
        config_prompt = self.config.get("llm", {}).get("planning_prompt_template", "")
        
        tool_metadata = self._get_analysis_tool_metadata(state)
        tools_list_str = self._format_tools_list_detailed(tool_metadata)
        scope_note = self._get_per_sim_tool_scope_note(state)
        input_files_block = self._format_trajectory_input_block(agent_input)
        goal_context = self._format_goal_context_for_planning(agent_input, state)
        
        # Build analysis context
        analysis_context = "\n".join([
            f"- Trajectory available: {bool(agent_input.trajectory_file)}",
            f"- Topology available: {bool(agent_input.topology_file)}",
            f"- Energy file available: {bool(agent_input.energy_file)}",
            f"- Requested analyses: {', '.join(agent_input.analyses) if agent_input.analyses else 'None specified'}",
            goal_context,
        ])
        
        # Extract PDB structural information if state provided
        pdb_info_str = self._format_pdb_info_for_llm(state) if state else ""
        
        # Use template from config or build basic prompt
        if config_prompt:
            return config_prompt.format(
                trajectory_file=agent_input.trajectory_file or "Not available",
                topology_file=agent_input.topology_file or "Not available",
                energy_file=agent_input.energy_file or "Not available",
                user_goal=agent_input.user_goal,
                enriched_goal=self._resolve_enriched_goal_for_planning(state, agent_input)
                or agent_input.user_goal
                or "Not specified",
                hpc_output_dir=agent_input.hpc_output_dir or "Not specified",
                analysis_context=analysis_context,
                tools_list=tools_list_str + ("\n\n" + scope_note if scope_note else ""),
            )
        else:
            # Fallback prompt if config template missing
            return f"""You are a molecular dynamics analysis expert. Create an analysis plan for:

**Available Data:**
- Topology: {agent_input.topology_file or "Not available"}
- Trajectory: {agent_input.trajectory_file or "Not available"}
- Energy File: {agent_input.energy_file or "Not available"}
- User Goal: {agent_input.user_goal}
{input_files_block}
{pdb_info_str}

**Available Tools:**
{tools_list_str}

{scope_note}
**CRITICAL:**
- You MUST ONLY use the tools listed above. Do NOT invent or suggest non-existent tools.
- For input file parameters (topology_file, trajectory_file, energy_file etc.):
  Use ONLY the file name (e.g. "md.gro"), NOT a full path.
  The framework resolves correct paths automatically.
- For output file parameters: Use ONLY the file name (e.g. "rmsd.dat").

Return JSON with: reasoning, overview, steps (name, description, tool_name, tool_params, reason)
"""

    def _extract_plan_json(self, content: str) -> Dict[str, Any]:
        """Extract and parse JSON plan from LLM response."""
        text = (content or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text).strip()

        def _try_parse(raw: str) -> Optional[Dict[str, Any]]:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, list):
                return self._coerce_tool_call_array_to_plan(parsed)
            if isinstance(parsed, dict):
                if "steps" not in parsed and parsed.get("tool_name"):
                    return self._coerce_tool_call_array_to_plan([parsed])
                return parsed
            return None

        result = _try_parse(text)
        if result is not None:
            return result

        for pattern in (r"\[[\s\S]*\]", r"\{[\s\S]*\}"):
            match = re.search(pattern, text)
            if match:
                result = _try_parse(match.group())
                if result is not None:
                    return result

        return {
            "reasoning": content,
            "overview": "MD trajectory analysis plan",
            "steps": [],
        }

    def _coerce_tool_call_array_to_plan(self, items: List[Any]) -> Dict[str, Any]:
        """Convert [{name, arguments}] tool-call JSON into a structured plan dict."""
        steps: List[Dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            tool_name = item.get("tool_name") or item.get("name") or ""
            params = dict(item.get("tool_params") or item.get("arguments") or {})
            steps.append(
                {
                    "name": item.get("name") or tool_name or "step",
                    "description": item.get("description", ""),
                    "tool_name": tool_name,
                    "tool_params": params,
                    "reason": item.get("reason", "LLM plan step"),
                }
            )
        return {
            "reasoning": "Converted from LLM tool-call array response",
            "overview": "MD trajectory analysis plan",
            "steps": steps,
            "potential_issues": ["LLM returned tool-call array instead of plan object"],
            "recommendations": [],
        }

    _BAD_TRAJECTORY_NAMES = frozenset(
        {"trajectory.dcd", "traj.dcd", "md.dcd", "trajectory.xtc", "topology.tpr"}
    )

    def _normalize_plan_steps(
        self,
        plan_dict: Dict[str, Any],
        agent_input: AnalysisAgentInput,
    ) -> Dict[str, Any]:
        """Repair common LLM parameter mistakes before tool execution."""
        topo = (
            Path(agent_input.topology_file).name
            if agent_input.topology_file
            else "md.tpr"
        )
        traj = (
            Path(agent_input.trajectory_file).name
            if agent_input.trajectory_file
            else "md.xtc"
        )
        traj_prefixes = ("calculate_", "analyze_", "wrap_trajectory")

        for step in plan_dict.get("steps") or []:
            if not isinstance(step, dict):
                continue
            tool = step.get("tool_name") or ""
            params = dict(step.get("tool_params") or {})

            if tool == "plot_md_data":
                for alias in ("data_file", "input_file", "csv_file"):
                    if alias in params and "data_files" not in params:
                        val = params.pop(alias)
                        params["data_files"] = [val] if isinstance(val, str) else val

            if tool == "plot_pca_projection":
                for alias in ("pca_file", "input_file", "pca_projections"):
                    if alias in params and "pca_projections_file" not in params:
                        val = params.pop(alias)
                        if val in ("pca.csv", "pca.dat"):
                            val = "pca_projections.dat"
                        params["pca_projections_file"] = val

            if tool == "calculate_trajectory_pca":
                params.pop("output_file", None)
                params.setdefault("projections_file", "pca_projections.dat")
                params.setdefault("variance_file", "pca_variance.dat")

            if tool == "calculate_free_energy_landscape":
                for alias in ("pca_file", "input_file"):
                    if alias in params and "pca_projections_file" not in params:
                        val = params.pop(alias)
                        if val in ("pca.csv", "pca.dat"):
                            val = "pca_projections.dat"
                        params["pca_projections_file"] = val

            needs_traj = any(tool.startswith(p) for p in traj_prefixes)
            if needs_traj:
                cur_traj = str(params.get("trajectory_file") or "").lower()
                if (
                    not params.get("topology_file")
                    or not params.get("trajectory_file")
                    or cur_traj in self._BAD_TRAJECTORY_NAMES
                    or cur_traj.endswith(".dcd")
                ):
                    params["topology_file"] = topo
                    params["trajectory_file"] = traj

            step["tool_params"] = params
        return plan_dict

    def replan_with_guidance(self, human_recommendation: str, state: dict) -> Optional[dict]:
        """Update the structured analysis plan by applying human guidance.

        If a current structured plan exists in state: sends it together with the human
        recommendation to the LLM so ONLY the requested changes are made (tool_params,
        steps, parameters).  Falls back to full re-planning via the normal prompt
        infrastructure when no current plan is available.

        Returns the updated plan dict, or None if the LLM call fails.
        """
        if not (self.llm and self.llm.available):
            return None

        import json as _j

        current_plan = (
            (state.get("execution_plan") or {})
            .get("structured_plans", {})
            .get("analysis")
        )

        if current_plan:
            # Modification mode: keep existing plan, apply targeted changes
            tool_metadata = self._get_analysis_tool_metadata(state)
            tools_str = self._format_tools_list_detailed(tool_metadata)
            scope_note = self._get_per_sim_tool_scope_note(state)
            prompt = (
                f"You are updating an MD trajectory analysis execution plan.\n\n"
                f"CURRENT PLAN (JSON):\n```json\n{_j.dumps(current_plan, indent=2)}\n```\n\n"
                f"HUMAN GUIDANCE (apply ONLY these changes):\n{human_recommendation}\n\n"
                f"{scope_note}\n"
                f"Available tools for reference (tool_name must match):\n{tools_str}\n\n"
                f"Rules:\n"
                f"- Apply ONLY the changes the human requested.\n"
                f"- Update tool_params values, add/remove/reorder steps as needed.\n"
                f"- Keep all other steps and fields exactly as they are.\n"
                f"- Preserve JSON structure: reasoning, overview, steps, potential_issues, recommendations.\n"
                f"- Each step must have: name, description, tool_name, tool_params, reason.\n"
                f"- Return ONLY valid JSON — no explanation, no markdown fences.\n"
            )
        else:
            # Fresh planning mode: build from planner NL instructions + human guidance
            nl_instructions = (
                (state.get("execution_plan") or {})
                .get("agent_plans", {})
                .get("analysis_agent", "")
            )
            augmented = (
                nl_instructions
                + "\n\n**HUMAN RECOMMENDATION (must be followed):**\n" + human_recommendation
            ) if nl_instructions else human_recommendation
            working_dir = state.get("working_directory", ".")
            hpc_output_dir = state.get("hpc_output_dir") or str(Path(working_dir) / "hpc")
            agent_input = AnalysisAgentInput(
                working_directory=working_dir,
                hpc_output_dir=hpc_output_dir,
                topology_file=state.get("topology"),
                trajectory_file=state.get("trajectory"),
                energy_file=state.get("energy_file"),
                user_goal=state.get("user_goal", ""),
                additional_instructions=augmented,
            )
            prompt = self._build_analysis_planning_prompt(agent_input, state)

        try:
            resp = self.llm.prompt_raw(prompt, temperature=0.1, max_tokens=16384, format="json")
            plan_dict = self._extract_plan_json(resp)
            if current_plan:
                return plan_dict
            plan_dict = self._normalize_plan_steps(plan_dict, agent_input)
            return plan_dict
        except Exception:
            return None

    def _create_fallback_analysis_plan(
        self,
        agent_input: AnalysisAgentInput,
        state: Optional[MDState] = None,
    ) -> AnalysisPlan:
        """
        Create template-based fallback plan when LLM fails.
        Respects explicit metric scope from the user goal when present.
        """
        if state and state.get("hitl_chat_task") and self._is_combined_hitl_context(state):
            return self._create_combined_hitl_fallback_plan(agent_input, state)

        steps: List[AnalysisStep] = []

        topo_name = Path(agent_input.topology_file).name if agent_input.topology_file else None
        traj_name = Path(agent_input.trajectory_file).name if agent_input.trajectory_file else None
        energy_name = Path(agent_input.energy_file).name if agent_input.energy_file else None

        _goal_lower = " ".join(collect_goal_texts_for_intent(state, agent_input)).lower()
        requested = self._intent_metrics(state, agent_input)
        if requested is None:
            requested = frozenset({"rmsd", "rmsf", "rg"})

        if traj_name and topo_name:
            if "rmsd" in requested:
                steps.extend([
                    AnalysisStep(
                        name="Calculate RMSD",
                        description="Calculate Root Mean Square Deviation to assess structural stability",
                        tool_name="calculate_rmsd",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "selection": "protein and name CA",
                            "output_file": "rmsd.dat",
                        },
                        reason="RMSD indicates structural stability over time",
                    ),
                    AnalysisStep(
                        name="Plot RMSD",
                        description="Plot RMSD time-series",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["rmsd.dat"],
                            "output_file": "rmsd.png",
                            "xlabel": "Time (ns)",
                            "ylabel": "RMSD (Å)",
                        },
                        reason="Visualise RMSD stability",
                    ),
                ])
            if "rmsf" in requested:
                steps.extend([
                    AnalysisStep(
                        name="Calculate RMSF",
                        description="Calculate Root Mean Square Fluctuation to identify flexible regions",
                        tool_name="calculate_rmsf",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "selection": "protein and name CA",
                            "output_file": "rmsf.dat",
                        },
                        reason="RMSF identifies flexible and rigid regions",
                    ),
                    AnalysisStep(
                        name="Plot RMSF",
                        description="Plot per-residue RMSF",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["rmsf.dat"],
                            "output_file": "rmsf.png",
                            "xlabel": "Residue",
                            "ylabel": "RMSF (Å)",
                        },
                        reason="Visualise per-residue flexibility",
                    ),
                ])
            if "rg" in requested:
                steps.extend([
                    AnalysisStep(
                        name="Calculate Radius of Gyration",
                        description="Calculate radius of gyration to assess protein compactness",
                        tool_name="calculate_radius_of_gyration",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "selection": "protein",
                            "output_file": "gyration.dat",
                        },
                        reason="Radius of gyration indicates protein compactness",
                    ),
                    AnalysisStep(
                        name="Plot Radius of Gyration",
                        description="Plot Rg time-series",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["gyration.dat"],
                            "output_file": "gyration.png",
                            "xlabel": "Time (ns)",
                            "ylabel": "Rg (Å)",
                        },
                        reason="Visualise compactness over time",
                    ),
                ])

            _lig_resname = (
                self._detect_ligand_resname(agent_input, state)
                if state
                else "ATP"
            )
            _is_holo = state and self._is_holo_simulation(state, agent_input)

            if "com" in requested and _is_holo:
                steps.extend([
                    AnalysisStep(
                        name="Ligand Pocket Distance",
                        description=(
                            f"Identify protein pocket atoms within 5 Å of {_lig_resname} at frame 0, "
                            "then track COM-to-COM distance over the trajectory"
                        ),
                        tool_name="calculate_ligand_pocket_distance",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "ligand_selection": f"resname {_lig_resname}",
                            "protein_selection": "protein",
                            "cutoff": 5.0,
                            "output_file": "ligand_pocket_distance.csv",
                        },
                        reason="Track whether ligand stays in binding pocket",
                    ),
                    AnalysisStep(
                        name="Plot Ligand Pocket Distance",
                        description="Plot ligand-to-pocket COM distance over time",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["ligand_pocket_distance.csv"],
                            "output_file": "ligand_pocket_distance.png",
                            "x_col": 1,
                            "y_col": 2,
                            "xlabel": "Time (ns)",
                            "ylabel": "COM Distance (Å)",
                        },
                        reason="Visualise ligand displacement from catalytic pocket",
                    ),
                ])

            if "contacts" in requested and _is_holo:
                steps.extend([
                    AnalysisStep(
                        name="Protein-Ligand Contacts",
                        description="Count protein–ligand H-bonds and heavy-atom contacts per frame",
                        tool_name="calculate_protein_ligand_contacts",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "ligand_selection": f"resname {_lig_resname}",
                            "output_file": "protein_ligand_contacts.csv",
                        },
                        reason="User requested protein–ligand contact analysis",
                    ),
                    AnalysisStep(
                        name="Plot Protein-Ligand Contacts",
                        description="Plot contact and H-bond counts over time",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["protein_ligand_contacts.csv"],
                            "output_file": "protein_ligand_contacts.png",
                            "xlabel": "Time (ns)",
                            "ylabel": "Count",
                        },
                        reason="Visualise protein–ligand interactions",
                    ),
                ])

            if "pocket_sasa" in requested and _is_holo:
                steps.extend([
                    AnalysisStep(
                        name="Pocket SASA",
                        description="Calculate solvent-accessible surface area of the binding pocket",
                        tool_name="calculate_pocket_sasa",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "ligand_selection": f"resname {_lig_resname}",
                            "output_file": "pocket_sasa.csv",
                        },
                        reason="User requested pocket SASA",
                    ),
                    AnalysisStep(
                        name="Plot Pocket SASA",
                        description="Plot pocket SASA over time",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["pocket_sasa.csv"],
                            "output_file": "pocket_sasa.png",
                            "xlabel": "Time (ns)",
                            "ylabel": "SASA (Å²)",
                        },
                        reason="Visualise pocket accessibility",
                    ),
                ])

            if "residence" in requested and _is_holo:
                steps.extend([
                    AnalysisStep(
                        name="Ligand Residence",
                        description="Analyze ligand residence time and unbinding events",
                        tool_name="analyze_ligand_residence",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "ligand_selection": f"resname {_lig_resname}",
                            "output_file": "ligand_residence.csv",
                        },
                        reason="User requested ligand residence/unbinding analysis",
                    ),
                    AnalysisStep(
                        name="Plot Ligand Residence",
                        description="Plot minimum protein–ligand contact distance over time",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["ligand_residence.csv"],
                            "output_file": "ligand_residence.png",
                            "xlabel": "Time (ns)",
                            "ylabel": "Min contact distance (Å)",
                        },
                        reason="Visualise ligand binding proximity",
                    ),
                ])

            if "pocket_rmsf" in requested and _is_holo:
                steps.extend([
                    AnalysisStep(
                        name="Pocket RMSF",
                        description="Calculate per-residue RMSF for binding-pocket residues",
                        tool_name="calculate_pocket_rmsf",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "ligand_selection": f"resname {_lig_resname}",
                            "output_file": "pocket_rmsf.dat",
                        },
                        reason="User requested pocket RMSF",
                    ),
                    AnalysisStep(
                        name="Plot Pocket RMSF",
                        description="Plot pocket residue flexibility",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["pocket_rmsf.dat"],
                            "output_file": "pocket_rmsf.png",
                            "xlabel": "Residue",
                            "ylabel": "RMSF (Å)",
                            "plot_type": "line",
                        },
                        reason="Visualise pocket flexibility",
                    ),
                ])

            if "ligand_rmsf" in requested and _is_holo:
                steps.extend([
                    AnalysisStep(
                        name="Ligand RMSF",
                        description="Calculate per-atom RMSF for the ligand",
                        tool_name="calculate_ligand_rmsf",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "ligand_selection": f"resname {_lig_resname}",
                            "output_file": "ligand_rmsf.dat",
                        },
                        reason="User requested ligand RMSF",
                    ),
                    AnalysisStep(
                        name="Plot Ligand RMSF",
                        description="Plot ligand atom flexibility",
                        tool_name="plot_md_data",
                        tool_params={
                            "data_files": ["ligand_rmsf.dat"],
                            "output_file": "ligand_rmsf.png",
                            "xlabel": "Atom",
                            "ylabel": "RMSF (Å)",
                            "plot_type": "bar",
                        },
                        reason="Visualise ligand flexibility",
                    ),
                ])

            if "pca" in requested:
                steps.extend([
                    AnalysisStep(
                        name="Trajectory PCA",
                        description="PCA on Cα coordinates to capture collective motions",
                        tool_name="calculate_trajectory_pca",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "selection": "protein and name CA",
                            "projections_file": "pca_projections.dat",
                            "variance_file": "pca_variance.dat",
                        },
                        reason="User requested PCA on Cα",
                    ),
                    AnalysisStep(
                        name="Plot PCA Projection",
                        description="PC1 vs PC2 scatter coloured by time",
                        tool_name="plot_pca_projection",
                        tool_params={
                            "pca_projections_file": "pca_projections.dat",
                            "output_file": "pca_pc1_pc2.png",
                        },
                        reason="Visualise PCA conformational sampling",
                    ),
                ])

            if "fel" in requested:
                steps.extend([
                    AnalysisStep(
                        name="Free-Energy Landscape",
                        description="Build FEL from PCA projections at 310 K",
                        tool_name="calculate_free_energy_landscape",
                        tool_params={
                            "pca_projections_file": "pca_projections.dat",
                            "temperature_k": 310.0,
                            "output_plot": "fel_pc1_pc2.png",
                            "output_grid": "fel_pc1_pc2_grid.csv",
                        },
                        reason="User requested free-energy landscape at 310 K",
                    ),
                    AnalysisStep(
                        name="FEL Basin Features",
                        description="Extract basin depths, barriers, and landscape entropy",
                        tool_name="analyze_fel_landscape_features",
                        tool_params={
                            "fel_grid_file": "fel_pc1_pc2_grid.csv",
                            "temperature_k": 310.0,
                            "output_json": "fel_features.json",
                            "output_csv": "fel_features.csv",
                            "output_basins_csv": "fel_basins.csv",
                            "output_plot": "fel_basins.png",
                        },
                        reason="User requested FEL basin features",
                    ),
                    AnalysisStep(
                        name="Export FEL Basin Structures",
                        description=(
                            "Write representative PDB per FEL basin for "
                            "visualising transient conformations"
                        ),
                        tool_name="export_fel_basin_structures",
                        tool_params={
                            "topology_file": topo_name,
                            "trajectory_file": traj_name,
                            "fel_features_file": "fel_features.json",
                            "pca_projections_file": "pca_projections.dat",
                            "manifest_file": "fel_basin_structures.csv",
                        },
                        reason="User requested FEL basin structures for highlighting",
                    ),
                ])

            _has_dccm_request = "dccm" in requested or any(
                kw in _goal_lower for kw in
                ["dccm", "cross-correlation", "cross correlation",
                 "correlated motion", "allosteric", "coupled motion"]
            )
            if _has_dccm_request:
                steps.append(AnalysisStep(
                    name="Calculate Dynamic Cross-Correlation Matrix (DCCM)",
                    description=(
                        "Compute normalised DCCM of Cα fluctuations to reveal correlated "
                        "and anti-correlated residue motions."
                    ),
                    tool_name="calculate_dccm",
                    tool_params={
                        "topology_file": topo_name,
                        "trajectory_file": traj_name,
                        "selection": "protein and name CA",
                        "output_prefix": "dccm",
                        "frame_interval": 5,
                        "save_matrix_csv": True,
                        "create_heatmap": True,
                    },
                    reason="DCCM reveals allosteric communication patterns",
                ))

        if energy_name and "energy" in requested:
            steps.extend([
                AnalysisStep(
                    name="Analyze Energy",
                    description="Extract and analyze energy terms from simulation",
                    tool_name="analyze_energy",
                    tool_params={"energy_file": energy_name, "output_file": "energy.dat"},
                    reason="Energy analysis assesses simulation stability",
                ),
                AnalysisStep(
                    name="Plot Energy",
                    description="Plot energy terms over time",
                    tool_name="plot_md_data",
                    tool_params={
                        "data_files": ["energy.dat"],
                        "output_file": "energy.png",
                        "xlabel": "Time (ns)",
                        "ylabel": "Energy (kJ/mol)",
                    },
                    reason="Visualise thermodynamic equilibration",
                ),
            ])

        if traj_name and topo_name and len(requested) >= 2:
            _panel_files: List[str] = []
            _panel_xl: List[str] = []
            _panel_yl: List[str] = []
            _panel_titles: List[str] = []
            _panel_map = {
                "rmsd": ("rmsd.dat", "Time (ns)", "RMSD (Å)", "RMSD"),
                "rmsf": ("rmsf.dat", "Residue", "RMSF (Å)", "RMSF"),
                "rg": ("gyration.dat", "Time (ns)", "Rg (Å)", "Radius of Gyration"),
                "energy": ("energy.dat", "Time (ns)", "Energy (kJ/mol)", "Energy"),
            }
            for metric in ("rmsd", "rmsf", "rg", "energy"):
                if metric in requested and metric in _panel_map:
                    f, xl, yl, tl = _panel_map[metric]
                    if metric != "energy" or energy_name:
                        _panel_files.append(f)
                        _panel_xl.append(xl)
                        _panel_yl.append(yl)
                        _panel_titles.append(tl)
            if len(_panel_files) >= 2:
                steps.append(AnalysisStep(
                    name="Create Combined Metrics Plot",
                    description="Multi-panel summary figure of requested metrics in one PNG.",
                    tool_name="plot_multipanel",
                    tool_params={
                        "data_files": _panel_files,
                        "output_file": "combined_metrics.png",
                        "layout": "vertical",
                        "titles": _panel_titles,
                        "xlabels": _panel_xl,
                        "ylabels": _panel_yl,
                    },
                    reason="Combined overview when multiple metrics were requested.",
                ))

        metrics_label = ", ".join(sorted(requested))
        return AnalysisPlan(
            reasoning=f"Intent-driven fallback plan for: {metrics_label}",
            overview=f"Trajectory analysis: {metrics_label}",
            steps=steps,
            potential_issues=["Requires trajectory and topology files"],
            recommendations=["Verify all files exist before execution"],
        )

    def _run_trajectory_batch_precache(
        self,
        plan: AnalysisPlan,
        state: MDState,
    ) -> Dict[int, Dict[str, Any]]:
        """Pre-compute trajectory metrics in minimal RAW/ALIGNED passes."""
        try:
            from src.analysis.trajectory_batch import (
                run_plan_trajectory_batches,
                summarize_batch_plan,
            )
        except ImportError:
            return {}

        input_map = self._resolve_input_files(state)
        topology = input_map.get("topology")
        trajectory = input_map.get("trajectory")
        if not topology or not trajectory:
            logger.info("Trajectory batching skipped: topology/trajectory not resolved")
            return {}

        prepared: Dict[int, Dict[str, Any]] = {}
        output_param_names = [
            "output_file", "output_prefix", "plot_file", "figure_path",
            "csv_file", "dat_file", "save_path", "output_csv", "output_fig",
        ]
        input_param_to_type = {
            "topology_file": "topology",
            "topology": "topology",
            "structure": "topology",
            "trajectory_file": "trajectory",
            "trajectory": "trajectory",
            "traj": "trajectory",
        }

        for idx, step in enumerate(plan.steps):
            params = sanitize_tool_output_params(dict(step.tool_params or {}))
            for pname in output_param_names:
                if pname in params and params[pname]:
                    params[pname] = os.path.basename(str(params[pname]))
            for pname, ftype in input_param_to_type.items():
                if pname in params and input_map.get(ftype):
                    params[pname] = input_map[ftype]
            params["working_dir"] = str(self.file_manager.agent_dir)
            prepared[idx] = params

        logger.info(summarize_batch_plan(plan.steps))
        return run_plan_trajectory_batches(
            plan.steps,
            topology_file=topology,
            trajectory_file=trajectory,
            working_dir=str(self.file_manager.agent_dir),
            prepared_params=prepared,
        )

    def _execute_analysis_plan(self, agent_input: AnalysisAgentInput, 
                               plan: AnalysisPlan,
                               state: MDState) -> AnalysisExecutionResult:
        """
        Execute analysis plan step-by-step using tool executor.
        Tracks outputs and handles errors gracefully.
        """
        execution_log = []
        issues = []
        warnings = []
        generated_files = {}
        results = {}
        
        # Get execution limits from config
        agent_config = self.config
        max_retries = agent_config.get("max_tool_retries", 2)
        max_steps = agent_config.get("max_total_steps", 20)
        fail_fast = agent_config.get("fail_fast", False)
        
        # Get analysis directory
        analysis_dir = state.get("analysis_directory", self.tool_executor.working_dir)
        
        try:
            # Enforce max steps limit
            if len(plan.steps) > max_steps:
                warnings.append(f"Plan has {len(plan.steps)} steps, limiting to {max_steps}")
                plan.steps = plan.steps[:max_steps]

            batch_results: Dict[int, Dict[str, Any]] = {}
            if agent_config.get("use_trajectory_batching", True):
                batch_results = self._run_trajectory_batch_precache(plan, state)
                if batch_results:
                    execution_log.append(
                        f"\n=== Trajectory batch pre-computed {len(batch_results)} metric(s) ==="
                    )
            
            for i, step in enumerate(plan.steps):
                # Validate tool name - skip invalid placeholder names
                invalid_tools = ["none", "manual", "skip", "custom", "placeholder", ""]
                if not step.tool_name or step.tool_name.lower() in invalid_tools:
                    skip_msg = f"Skipping step {i+1} '{step.name}': invalid tool name '{step.tool_name}'"
                    execution_log.append(f"\n⚠ {skip_msg}")
                    warnings.append(skip_msg)
                    log_agent_action("analysis", f"Step {i+1}/{len(plan.steps)} skipped", {
                        "step": step.name,
                        "reason": f"Invalid tool name: {step.tool_name}"
                    })
                    continue

                if is_combined_analysis_tool(step.tool_name):
                    if not self._is_combined_hitl_context(state):
                        skip_msg = (
                            f"Skipping step {i+1} '{step.name}': '{step.tool_name}' is a "
                            "cross-simulation tool and cannot run in per-simulation analysis"
                        )
                        execution_log.append(f"\n⚠ {skip_msg}")
                        warnings.append(skip_msg)
                        log_agent_action("analysis", f"Step {i+1}/{len(plan.steps)} skipped", {
                            "step": step.name,
                            "reason": f"Combined-analysis tool not allowed: {step.tool_name}",
                        })
                        continue
                
                # Log step start
                log_agent_action("analysis", f"Executing step {i+1}/{len(plan.steps)}", {
                    "step": step.name,
                    "tool": step.tool_name
                })
                
                execution_log.append(f"\n--- Step {i+1}: {step.name} ---")
                execution_log.append(f"Description: {step.description}")
                execution_log.append(f"Tool: {step.tool_name}")
                execution_log.append(f"Reason: {step.reason}")
                
                # Prepare tool parameters
                tool_params = dict(step.tool_params) if step.tool_params else {}

                if is_combined_analysis_tool(step.tool_name):
                    task_text = state.get("hitl_chat_task") or agent_input.user_goal or ""
                    tool_params = self._resolve_combined_tool_sim_dirs(state, task_text, tool_params)
                
                # SECURITY: Sanitize output parameters (LLM may specify full paths)
                tool_params = sanitize_tool_output_params(tool_params)
                
                # ── FORCE-OVERRIDE input file paths ──────────────────────
                # The LLM often invents wrong paths.  We ignore whatever
                # the LLM put in tool_params for input files and inject
                # the real paths from state (which point to working_dir/hpc/
                # or wherever the files actually live).
                #
                # 1. Build a map: canonical type → resolved absolute path
                _state_input_map = self._resolve_input_files(state)
                
                # 2. For every recognised input-param name, override with
                #    the correct path from the map (or scan input dir).
                _INPUT_PARAM_TO_TYPE = {
                    "topology_file": "topology",
                    "topology": "topology",
                    "structure": "topology",
                    "trajectory_file": "trajectory",
                    "trajectory": "trajectory",
                    "traj": "trajectory",
                    "energy_file": "energy",
                    "edr": "energy",
                    "edr_file": "energy",
                }
                
                for param_name, file_type in _INPUT_PARAM_TO_TYPE.items():
                    if param_name in tool_params:
                        resolved = _state_input_map.get(file_type)
                        if resolved:
                            tool_params[param_name] = resolved
                            logger.debug(f"  {param_name}: overridden → {resolved}")
                        else:
                            # Last resort: try resolve_input_file with LLM's filename
                            file_ref = str(tool_params[param_name])
                            resolved_path = self.file_manager.resolve_input_file(
                                file_reference=file_ref,
                                search_stages=["hpc", "simsetup", "preprocess"]
                            )
                            if resolved_path:
                                tool_params[param_name] = resolved_path
                                logger.debug(f"  {param_name}: registry → {resolved_path}")
                            else:
                                logger.warning(f"  {param_name}: could not resolve '{file_ref}'")
                
                # ── Prepend agent directory to output parameters ──────────
                output_param_names = [
                    "output_file", "output_prefix", "plot_file", "figure_path",
                    "csv_file", "dat_file", "save_path", "output_csv", "output_fig"
                ]
                
                for param_name in output_param_names:
                    if param_name in tool_params and tool_params[param_name]:
                        # Convert filename to full path in agent's directory
                        filename = str(tool_params[param_name])
                        full_path = self.file_manager.get_agent_path(filename)
                        tool_params[param_name] = full_path
                        logger.debug(f"  {param_name}: {filename} -> {full_path}")
                
                # CRITICAL: Always use the analysis agent directory for working_dir
                # LLMs may suggest workspace root, but tools must run in analysis subdirectory
                tool_params["working_dir"] = self.file_manager.agent_dir
                logger.debug(f"  Set working_dir to analysis agent directory: {self.file_manager.agent_dir}")

                # Resolve list-type file parameters (e.g. data_files for plot tools).
                # LLMs often pass wrong absolute paths; normalise to agent_dir/<basename>.
                list_file_params = ["data_files", "input_files", "file_list"]
                for lp in list_file_params:
                    if lp in tool_params and isinstance(tool_params[lp], list):
                        resolved_list = []
                        agent_dir = str(self.file_manager.agent_dir)
                        for fref in tool_params[lp]:
                            fref = str(fref)
                            basename = os.path.basename(fref)
                            resolved_list.append(os.path.join(agent_dir, basename))
                        logger.debug(f"  Resolved {lp}: {tool_params[lp]} -> {resolved_list}")
                        tool_params[lp] = resolved_list
                
                execution_log.append(f"Parameters: {json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in tool_params.items()}, indent=2)}")
                
                # Use batched trajectory result when available
                if i in batch_results and batch_results[i].get("success"):
                    result = batch_results[i]
                    execution_log.append(
                        f"✓ Success (trajectory batch): {result.get('message', 'Step completed')}"
                    )
                else:
                    # Execute tool with retry logic (or retry after batch failure)
                    retry_count = 0
                    result = None
                    
                    while retry_count <= max_retries:
                        result = self.tool_executor.execute(step.tool_name, **tool_params)
                        
                        if result.get("success"):
                            break
                        
                        retry_count += 1
                        if retry_count <= max_retries:
                            execution_log.append(f"⚠ Retry {retry_count}/{max_retries}: {result.get('error')}")
                        else:
                            execution_log.append(f"✗ Max retries ({max_retries}) exceeded")
                
                # Process results
                if result and result.get("success"):
                    execution_log.append(f"✓ Success: {result.get('message', 'Step completed')}")
                    
                    # Store analysis results
                    analysis_name = step.name.lower().replace(" ", "_")
                    results[analysis_name] = result
                    
                    # Track and register generated files using SecureFileManager
                    file_keys = ["output_file", "plot_file", "csv_file", "heatmap_file", 
                                "timeseries_file", "figure_path"]
                    
                    for file_key in file_keys:
                        if file_key in result and result[file_key]:
                            file_path = result[file_key]
                            
                            # Register using file manager (automatic tracking)
                            file_type = self._classify_file_type(file_key, file_path)
                            self.file_manager.register_external_file(
                                file_path=file_path,
                                file_type=file_type,
                                description=f"{step.name}: {step.description}"
                            )
                            
                            generated_files[file_path] = step.description
                            log_file_operation("analysis", "create", file_path, True)
                    
                    # Also handle output_files dict (common in tools like DSSP)
                    if "output_files" in result and isinstance(result["output_files"], dict):
                        for out_name, out_path in result["output_files"].items():
                            if out_path and Path(out_path).exists():
                                file_type = self._classify_file_type(out_name, out_path)
                                self.file_manager.register_external_file(
                                    file_path=out_path,
                                    file_type=file_type,
                                    description=f"{step.name} {out_name}"
                                )
                                generated_files[out_path] = f"{step.name} {out_name}"
                                log_file_operation("analysis", "create", out_path, True)
                    
                    log_agent_action("analysis", f"Step {i+1}/{len(plan.steps)} completed", {
                        "step": step.name,
                        "tool": step.tool_name,
                        "status": "✅ SUCCESS"
                    })
                    
                    if result.get("warning"):
                        warnings.append(f"{step.name}: {result['warning']}")
                else:
                    error_msg = result.get('error', 'Failed to execute') if result else 'Tool execution failed'
                    execution_log.append(f"✗ Failed after {retry_count} attempts: {error_msg}")
                    issues.append(f"{step.name}: {error_msg}")
                    
                    log_agent_action("analysis", f"Step {i+1}/{len(plan.steps)} failed", {
                        "step": step.name,
                        "tool": step.tool_name,
                        "status": "❌ FAILED",
                        "error": error_msg
                    })
                    
                    if fail_fast:
                        execution_log.append("⚠ Stopping execution (fail_fast enabled)")
                        break
            
            execution_log_str = "\n".join(execution_log)
            
            # Generate execution report
            report = self._generate_execution_report(plan, results, issues, warnings)
            
            return AnalysisExecutionResult(
                success=len(issues) == 0,
                analyses_completed=[step.name for step in plan.steps if step.name.lower().replace(" ", "_") in results],
                results=results,
                output_directory=analysis_dir,
                report=report,
                issues=issues,
                warnings=warnings,
                generated_files=generated_files,
                execution_log=execution_log_str
            )
            
        except Exception as e:
            return AnalysisExecutionResult(
                success=False,
                output_directory=analysis_dir,
                report=f"Analysis failed: {str(e)}",
                issues=[str(e)],
                warnings=warnings,
                generated_files=generated_files,
                execution_log="\n".join(execution_log)
            )

    def _generate_execution_report(self, plan: AnalysisPlan, results: Dict[str, Any],
                                   issues: list, warnings: list) -> str:
        """Generate human-readable execution report"""
        report_lines = [
            "=" * 80,
            "MD TRAJECTORY ANALYSIS REPORT",
            "=" * 80,
            "",
            f"Plan Overview: {plan.overview}",
            f"Total Steps: {len(plan.steps)}",
            f"Completed: {len(results)}",
            f"Issues: {len(issues)}",
            f"Warnings: {len(warnings)}",
            "",
            "=" * 80,
            "RESULTS SUMMARY",
            "=" * 80,
        ]
        
        for analysis_name, result in results.items():
            report_lines.append(f"\n{analysis_name.upper()}:")
            if "message" in result:
                report_lines.append(f"  {result['message']}")
            
            # Add specific metrics based on analysis type
            if "rmsd" in analysis_name.lower() and "mean_rmsd" in result:
                report_lines.append(f"  Mean RMSD: {result['mean_rmsd']:.2f} Å")
            elif "rmsf" in analysis_name.lower() and "mean_rmsf" in result:
                report_lines.append(f"  Mean RMSF: {result['mean_rmsf']:.2f} Å")
            elif "gyration" in analysis_name.lower() and "mean_rg" in result:
                report_lines.append(f"  Mean Rg: {result['mean_rg']:.2f} Å")
        
        if issues:
            report_lines.extend([
                "",
                "=" * 80,
                "ISSUES ENCOUNTERED",
                "=" * 80,
            ])
            for issue in issues:
                report_lines.append(f"  • {issue}")
        
        if warnings:
            report_lines.extend([
                "",
                "=" * 80,
                "WARNINGS",
                "=" * 80,
            ])
            for warning in warnings:
                report_lines.append(f"  • {warning}")
        
        report_lines.append("\n" + "=" * 80)
        
        return "\n".join(report_lines)

    # ------------------------------------------------------------------
    # Input-path resolution helpers
    # ------------------------------------------------------------------

    def _resolve_input_files(self, state: MDState) -> Dict[str, str]:
        """Resolve canonical input file paths for the analysis agent.

        Returns a dict keyed by file type ("topology", "trajectory", "energy")
        with absolute paths that actually exist on disk.  Resolution order:

        1. State fields set by upstream agents (``topology``, ``trajectory_path``,
           ``energy_file``).
        2. Files copied into the analysis directory by
           ``_copy_files_from_hpc_secure``.
        3. Scan the hardcoded input directory (``working_dir/hpc/``) for common
           extensions.
        """
        from ..state import AGENT_IO_MAP

        resolved: Dict[str, str] = {}
        working_dir = state.get("working_directory", "working_dir")

        # Hardcoded input directory for this agent
        input_subdir = AGENT_IO_MAP.get("analysis", {}).get("input_dir", "hpc")
        input_dir = str(Path(working_dir) / input_subdir) if input_subdir else working_dir

        # --- 1. Try state fields first (set by HPC / simsetup agent) --------
        _STATE_KEYS = {
            "topology":   ["topology", "coordinates", "cleaned_pdb"],
            "trajectory":  ["trajectory_path"],
            "energy":      ["energy_file"],
        }
        for ftype, keys in _STATE_KEYS.items():
            for key in keys:
                val = state.get(key)
                if val and Path(val).is_file():
                    resolved[ftype] = str(Path(val).resolve())
                    logger.debug(f"_resolve_input_files: {ftype} from state['{key}'] → {resolved[ftype]}")
                    break

        # --- 2. Try files already in analysis_dir (copied earlier) -----------
        analysis_dir = state.get("analysis_dir") or self.file_manager.agent_dir
        _EXT_MAP = {
            "topology":   [".gro", ".pdb", ".tpr", ".top"],
            "trajectory":  [".xtc", ".trr", ".dcd", ".nc"],
            "energy":      [".edr", ".ene"],
        }
        for ftype, exts in _EXT_MAP.items():
            if ftype in resolved:
                continue
            for ext in exts:
                candidates = sorted(Path(analysis_dir).glob(f"*{ext}"))
                if candidates:
                    resolved[ftype] = str(candidates[0].resolve())
                    logger.debug(f"_resolve_input_files: {ftype} from analysis_dir → {resolved[ftype]}")
                    break

        # --- 3. Scan the hardcoded input directory (hpc/) --------------------
        for ftype, exts in _EXT_MAP.items():
            if ftype in resolved:
                continue
            for ext in exts:
                candidates = sorted(Path(input_dir).glob(f"*{ext}"))
                if candidates:
                    resolved[ftype] = str(candidates[0].resolve())
                    logger.debug(f"_resolve_input_files: {ftype} from input_dir({input_dir}) → {resolved[ftype]}")
                    break

        if not resolved:
            logger.warning("_resolve_input_files: no input files resolved")
        else:
            logger.info(f"_resolve_input_files: resolved {list(resolved.keys())}")

        return resolved

    def _classify_file_type(self, key_or_extension: str, file_path: str = "") -> str:
        """Classify file type based on parameter name or extension."""
        
        key_lower = key_or_extension.lower()
        path_lower = file_path.lower()
        
        # Classify by parameter name/key
        if "plot" in key_lower or "figure" in key_lower or "heatmap" in key_lower or "timeseries" in key_lower:
            return "plot"
        elif "trajectory" in key_lower or "traj" in key_lower:
            return "trajectory"
        elif "topology" in key_lower or "structure" in key_lower:
            return "topology"
        elif "energy" in key_lower:
            return "energy"
        
        # Classify by file extension
        if path_lower.endswith((".png", ".pdf", ".svg", ".jpg")):
            return "plot"
        elif path_lower.endswith(".xtc") or path_lower.endswith(".trr"):
            return "trajectory"
        elif path_lower.endswith((".gro", ".pdb", ".tpr")):
            return "topology"
        elif path_lower.endswith(".edr"):
            return "energy"
        elif path_lower.endswith((".csv", ".dat", ".xvg")):
            return "data"
        else:
            return "output"

    # ========== Legacy methods (kept for backward compatibility) ==========

    def _create_analysis_plan(self, state: MDState) -> Dict[str, Any]:
        """Legacy method for backward compatibility"""
        traj = state.get("trajectory_path")
        coords = state.get("coordinates")
        request = state.get("analysis_request") or "General stability and energy analysis"
        prompt = f"""
You are an expert MD analysis agent. Draft a practical analysis plan.

INPUTS:
- Trajectory: {traj}
- Coordinates: {coords}
- Request: {request}
- Preferred metrics: {self.config.get('metrics')}

RESPONSE FORMAT:
Metrics: [comma separated list]
Steps:
- Step 1: description
- Step 2: description
Outputs: [files/plots]
Notes: [assumptions/fallbacks]
"""
        resp = self.llm.prompt(prompt, system="You plan MD analysis tasks and ensure reproducible outputs.")
        return {"raw": resp}

    def _execute_basic_analysis(self, state: MDState, plan: Dict[str, Any]) -> None:
        """Legacy method for backward compatibility"""
        out_dir = self.config.get("output_dir", "./working_dir/analysis")
        os.makedirs(out_dir, exist_ok=True)
        traj = state.get("trajectory_path")
        coords = state.get("coordinates") or state.get("topology")

        results = state.setdefault("analysis_results", {})
        if not traj or not os.path.exists(traj):
            results["summary"] = "No trajectory available; stored analysis plan only."
            state["warnings"].append("Trajectory missing; analysis not executed")
            return

        # Minimal, dependency-light analysis placeholder
        if not HAS_MDA or not self.config.get("use_mdanalysis", True):
            results["summary"] = "MDAnalysis unavailable; minimal placeholder analysis done."
            results["metrics"] = {"frames": self._count_lines(traj)}
            return

        # Basic RMSD using MDAnalysis
        try:
            import numpy as np
            u = mda.Universe(coords, traj) if coords else mda.Universe(traj)
            ref = u.select_atoms("protein").positions.copy() if u.atoms.n_atoms > 0 else None
            rmsds = []
            for ts in u.trajectory:
                sel = u.select_atoms("protein")
                if sel.n_atoms == 0 or ref is None:
                    continue
                pos = sel.positions
                diff = pos - ref
                rmsd = (np.sqrt((diff * diff).sum(axis=1).mean()))
                rmsds.append(float(rmsd))
            results["metrics"] = {"rmsd_mean": float(np.mean(rmsds)) if rmsds else None,
                                   "rmsd_max": float(np.max(rmsds)) if rmsds else None,
                                   "frames": len(rmsds)}
            results["summary"] = "Computed simple RMSD over protein selection."
        except Exception as e:
            logger.exception("Error during MDAnalysis RMSD")
            state["errors"].append(f"RMSD analysis failed: {e}")

    def _count_lines(self, path: str) -> int:
        """Legacy helper for counting lines in a file"""
        try:
            with open(path, "rb") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
