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
from typing import Dict, Any, Optional
from pathlib import Path

from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_supervisor_routing, log_agent_start, log_llm_interaction,
    log_agent_action, log_file_operation, log_agent_completion, log_error,
    SecureFileManager, sanitize_tool_output_params
)
from .schemas import (
    AnalysisPlan, AnalysisStep,
    AnalysisResult as AnalysisExecutionResult,
    AnalysisAgentInput, AnalysisAgentOutput
)
from .tools import AnalysisToolExecutor, get_tool_metadata, is_combined_analysis_tool

logger = logging.getLogger(__name__)

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

    def _get_analysis_tool_metadata(self, state: Optional[MDState] = None) -> Dict[str, Dict[str, Any]]:
        """Per-simulation tool metadata for LLM planning (excludes combined-analysis tools)."""
        working_dir = state.get("working_directory") if state else None
        include_combined = bool(
            state and state.get("multi_sim_phase") == "combined_analysis"
        )
        return get_tool_metadata(
            working_directory=working_dir,
            include_combined=include_combined,
        )

    def _format_tools_list_for_prompt(self, tool_metadata: Dict[str, Dict[str, Any]]) -> str:
        """Format tool metadata as a prompt-friendly bullet list."""
        tools_list = []
        for tool_info in tool_metadata.values():
            tool_entry = f"→ {tool_info['name']}: {tool_info['description']}"
            tools_list.append(tool_entry)
        return "\n".join(tools_list)

    def _format_tools_list_detailed(self, tool_metadata: Dict[str, Dict[str, Any]]) -> str:
        """Format tool metadata with parameter details for standard planning prompts."""
        tools_list = []
        for tool_info in tool_metadata.values():
            tool_entry = f"→ {tool_info['name']}\n"
            tool_entry += f"  {tool_info['description']}\n"
            if tool_info.get("args"):
                tool_entry += "  Parameters:\n"
                for arg_name, arg_details in tool_info["args"].items():
                    required = "required" if arg_details["required"] else "optional"
                    desc = arg_details.get("description", "No description")
                    tool_entry += f"    • {arg_name} ({required}): {desc}\n"
            tools_list.append(tool_entry)
        return "\n".join(tools_list)

    def _get_per_sim_tool_scope_note(self, state: Optional[MDState] = None) -> str:
        """Tell the analysis LLM to stay within this simulation's scope."""
        if state and state.get("multi_sim_phase") == "combined_analysis":
            return ""
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
                if state.get("human_in_loop"):
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

    # ── Combined multi-sim analysis ───────────────────────────────────────

    def _run_combined_analysis(self, state: MDState) -> MDState:
        """
        Run cross-simulation combined analysis.

        Collects per-sim data files, produces overlay plots and stats CSVs
        in ``{working_directory}/analysis/``, and stores the results in state
        so the reporter can embed them in the combined report.
        """
        from .tools import run_combined_analysis, collect_metric_files

        working_dir = state.get("working_directory", "working_dir")
        analysis_dir = str(Path(working_dir) / "analysis")
        Path(analysis_dir).mkdir(parents=True, exist_ok=True)
        state["analysis_dir"] = analysis_dir
        state["analysis_directory"] = analysis_dir

        # Resolve per-sim directories and labels from completed_sim_states
        completed = state.get("completed_sim_states") or []
        sim_dirs = [s["working_directory"] for s in completed if s.get("working_directory")]
        labels = [s.get("label", f"sim_{i}") for i, s in enumerate(completed)]

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

            # Skip all-simulation RMSF overlay when apo/holo pairs exist —
            # per-protein RMSF comparison is clearer for ligand-effect studies.
            combined_metrics = ["rmsd", "rmsf", "rg", "energy"]
            if apo_holo_pairs:
                combined_metrics = ["rmsd", "rg", "energy"]

            result = run_combined_analysis.func(
                sim_dirs=sim_dirs,
                labels=labels,
                working_dir=analysis_dir,
                metrics=combined_metrics,
            )

            plots = result.get("plots", [])
            tables = result.get("tables", [])
            skipped = result.get("skipped", [])

            log_agent_action(
                agent_name="analysis",
                action="Combined Analysis Complete",
                details={
                    "plots": plots,
                    "tables": tables,
                    "skipped": skipped,
                    "summary": result.get("summary", ""),
                },
            )

            # ── Per-protein RMSF apo vs holo ──────────────────────────────
            rmsf_apo_holo_plots: list = []
            if apo_holo_pairs:
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

            if apo_holo_pairs:
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
            else:
                # Fallback: all-simulation comparison when pairing is unavailable
                try:
                    dccm_cmp = run_combined_dccm_analysis.func(
                        sim_dirs=sim_dirs,
                        labels=labels,
                        working_dir=analysis_dir,
                        output_file="dccm_comparison.png",
                    )
                    if dccm_cmp.get("success"):
                        dccm_plots.append(dccm_cmp["output_path"])
                        log_agent_action(
                            "analysis", "DCCM comparison generated",
                            {"output": dccm_cmp.get("output_path")},
                        )
                    else:
                        logger.warning(f"DCCM comparison: {dccm_cmp.get('message')}")
                except Exception as _exc:
                    logger.warning(f"DCCM comparison failed: {_exc}")

            # ── RMSF segment bar plots (from user-specified residue ranges) ─
            segment_plots: list = []
            try:
                if apo_holo_pairs:
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
                com_result = run_combined_com_distance_analysis.func(
                    sim_dirs=sim_dirs,
                    labels=labels,
                    working_dir=analysis_dir,
                )
                if com_result.get("success"):
                    com_plot = com_result.get("output_path")
                    if com_plot and com_plot not in plots:
                        plots.append(com_plot)
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

            # ── DSSP: backfill missing per-sim runs, comparison chart, activation-loop heatmaps ─
            dssp_plots: list = []
            try:
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
            state["next_node"] = "supervisor"

        except Exception as exc:
            import traceback
            logger.error(f"Combined analysis failed: {exc}\n{traceback.format_exc()}")
            state["errors"].append(f"Combined analysis error: {exc}")
            state["next_node"] = "supervisor"   # Let supervisor decide what to do

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
                "reasoning": plan.reasoning[:200]
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

    def _create_analysis_plan_llm(self, agent_input: AnalysisAgentInput, state: MDState) -> AnalysisPlan:
        """
        Use LLM to analyze available data and create intelligent analysis plan.
        Falls back to template-based plan if LLM fails.
        """
        # Build LLM prompt from config template
        prompt = self._build_analysis_planning_prompt(agent_input, state)
        
        try:
            response = self.llm.invoke([prompt])
            content = response.content or ""
            
            log_llm_interaction("analysis.planning", prompt, content,
                              is_mock=hasattr(self.llm, '_is_mock_mode') and self.llm._is_mock_mode)
            
            # Parse LLM response into structured plan
            plan_dict = self._extract_plan_json(content)

            # Post-process: inject mandatory steps the LLM may have omitted
            # (e.g. calculate_ligand_pocket_distance when user goal mentions ATP/pocket)
            plan_dict = self._inject_mandatory_steps(plan_dict, agent_input, state)

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
            return self._create_fallback_analysis_plan(agent_input)

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
        return is_holo_simulation(sim_dir, label)

    def _inject_mandatory_steps(self, plan_dict: Dict[str, Any],
                                 agent_input: AnalysisAgentInput,
                                 state: MDState) -> Dict[str, Any]:
        """Post-process the LLM plan to inject mandatory steps that the LLM may have omitted.

        Currently handles:
        - calculate_ligand_pocket_distance + plot_md_data when the user goal
          mentions ligand/ATP/pocket/COM distance but the LLM left it out.
        """
        steps = plan_dict.get("steps", [])

        # --- Ligand pocket distance ---
        existing_tools = {s.get("tool_name", "") for s in steps}
        if "calculate_ligand_pocket_distance" not in existing_tools:
            # Check if user goal mentions ligand/COM/pocket keywords
            user_goal = (
                state.get("user_goal_original") or
                state.get("user_goal") or
                agent_input.user_goal or
                ""
            ).lower()
            ligand_keywords = [
                "ligand", "atp", "adp", "amp", "gtp", "gdp", "nad",
                "inhibitor", "pocket", "com distance", "center of mass",
                "center-of-mass", "binding site", "catalytic pocket",
                "catalytic site", "active site",
            ]
            needs_pocket_distance = any(kw in user_goal for kw in ligand_keywords)

            # Also trigger if pdb_analysis shows a ligand is present
            if not needs_pocket_distance:
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
                    "triggered by user_goal keywords"
                )

        # --- DCCM ---
        if "calculate_dccm" not in existing_tools:
            user_goal_lower = (
                state.get("user_goal_original") or
                state.get("user_goal") or
                agent_input.user_goal or
                ""
            ).lower()
            dccm_keywords = [
                "dccm", "cross-correlation", "cross correlation",
                "correlated motion", "allosteric", "coupled motion",
                "dynamics variation", "pseudokinase",
                "dccm difference", "dccm diff", "effect of atp",
                "ligand effect", "protein only", "protein+atp",
            ]
            needs_dccm = any(kw in user_goal_lower for kw in dccm_keywords)

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
            # Inject multipanel only when ≥2 standard panels are available
            if len(panel_files) >= 2:
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
        tools_list_str = self._format_tools_list_for_prompt(tool_metadata)
        scope_note = self._get_per_sim_tool_scope_note(state)
        
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
- User Goal: {agent_input.user_goal or "Not specified"}
{registry_str}
{pdb_info_str}

**DETAILED INSTRUCTIONS FROM PLANNER:**
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
  Use ONLY the file name (e.g. "md.gro"), NOT a full path.
  The framework resolves correct paths automatically. Do NOT invent directory paths.
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
- **LIGAND POCKET DISTANCE (MANDATORY WHEN REQUESTED):**
  If the **User Goal** above contains ANY of these keywords:
  "ligand", "ATP", "ADP", "inhibitor", "pocket", "COM", "center of mass",
  "center-of-mass", "binding site", "catalytic pocket", "active site", "distance"
  — you MUST include calculate_ligand_pocket_distance → plot_md_data pair.
  NOTE: The planner's instructions may NOT have explicitly mentioned this step.
  You MUST follow the User Goal, not just the planner's text.
  For ligand_selection use the residue name from the trajectory topology
  (e.g. "resname ATP"). Use cutoff 5.0 (Å).
- **DCCM — DYNAMIC CROSS-CORRELATION MATRIX (include when relevant):**
  If the **User Goal** mentions ANY of: "DCCM", "cross-correlation", "correlated motion",
  "allosteric", "coupled motions", "dynamics variation", "pseudokinase"
  — include calculate_dccm (it generates its own heatmap PNG internally — no
  separate plot_md_data step required for DCCM).
  Use: selection="protein and name CA", frame_interval=5, output_prefix="dccm".

Your task: Create a detailed, step-by-step execution plan that follows the planner's instructions above
AND honours the original User Goal. When the User Goal requests ligand/pocket/COM distance analysis,
include calculate_ligand_pocket_distance even if the planner did not explicitly mention it.
The plan should specify which tools to call and in what order to achieve the planner's objectives.
ONLY include steps that use valid tools from the list above.

Output as JSON with this structure:
{{
  "reasoning": "How you'll implement the planner's instructions",
  "overview": "High-level summary",
  "steps": [
    {{
      "name": "step name",
      "description": "what it does",
      "tool_name": "tool to call",
      "tool_params": {{"param": "value"}},
      "reason": "why it's needed per planner's instructions"
    }}
  ],
  "potential_issues": ["issue1"],
  "recommendations": ["rec1"]
}}
"""

    def _build_standard_analysis_prompt(self, agent_input: AnalysisAgentInput, state: MDState = None) -> str:
        """Build LLM planning prompt from config template using dynamic tool metadata"""
        config_prompt = self.config.get("llm", {}).get("planning_prompt_template", "")
        
        tool_metadata = self._get_analysis_tool_metadata(state)
        tools_list_str = self._format_tools_list_detailed(tool_metadata)
        scope_note = self._get_per_sim_tool_scope_note(state)
        
        # Build analysis context
        analysis_context = "\n".join([
            f"- Trajectory available: {bool(agent_input.trajectory_file)}",
            f"- Topology available: {bool(agent_input.topology_file)}",
            f"- Energy file available: {bool(agent_input.energy_file)}",
            f"- Requested analyses: {', '.join(agent_input.analyses) if agent_input.analyses else 'None specified'}"
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
        """Extract and parse JSON plan from LLM response"""
        # Try to find JSON block in response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Fallback: return minimal structure
        return {
            "reasoning": content,
            "overview": "MD trajectory analysis plan",
            "steps": []
        }

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
            tools_list = [
                f"→ {t['name']}: {t['description']}"
                for t in tool_metadata.values()
            ]
            tools_str = "\n".join(tools_list)
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
            resp = self.llm.prompt(prompt, temperature=0.1)
            return self._extract_plan_json(resp)
        except Exception:
            return None

    def _create_fallback_analysis_plan(self, agent_input: AnalysisAgentInput) -> AnalysisPlan:
        """
        Create template-based fallback plan when LLM fails.
        Uses standard MD analysis workflow.
        File paths use filenames only — _execute_analysis_plan resolves them.
        """
        steps = []

        # Extract just the filenames — the execution engine resolves full paths
        topo_name = Path(agent_input.topology_file).name if agent_input.topology_file else None
        traj_name = Path(agent_input.trajectory_file).name if agent_input.trajectory_file else None
        energy_name = Path(agent_input.energy_file).name if agent_input.energy_file else None

        # Detect whether a ligand analysis was requested from the user goal text
        _goal_lower = (agent_input.user_goal or "").lower()
        _has_ligand_request = any(
            kw in _goal_lower for kw in
            ["ligand", "atp", "adp", "inhibitor", "pocket", "distance", "com distance", "binding"]
        )
        # Try to extract ligand residue name (e.g. "resname ATP") from the goal
        import re as _re_fb
        _lig_resname_match = _re_fb.search(
            r'resname[\s:]+([A-Za-z0-9]{1,6})', _goal_lower
        ) or _re_fb.search(
            r'\b(ATP|ADP|LIG|INH|NAD|FAD|GTP|GDP|AMP|MG|ION)\b', agent_input.user_goal or ""
        )
        _lig_resname = _lig_resname_match.group(1).upper() if _lig_resname_match else "LIG"

        # Detect whether a DCCM analysis was requested from the user goal text
        _has_dccm_request = any(
            kw in _goal_lower for kw in
            ["dccm", "cross-correlation", "cross correlation",
             "correlated motion", "allosteric", "coupled motion",
             "dynamics variation", "pseudokinase"]
        )
        if traj_name and topo_name:
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
                    reason="RMSD indicates structural stability over time"
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
                    reason="Visualise RMSD stability"
                ),
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
                    reason="RMSF identifies flexible and rigid regions"
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
                    reason="Visualise per-residue flexibility"
                ),
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
                    reason="Radius of gyration indicates protein compactness"
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
                    reason="Visualise compactness over time"
                ),
            ])

            # Ligand pocket distance — holo simulations only (apo has no ligand)
            if _has_ligand_request and self._is_holo_simulation(state, agent_input):
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
                        reason="Track whether ligand stays in binding pocket"
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
                        reason="Visualise ligand displacement from catalytic pocket"
                    ),
                ])

            # DCCM — when user mentioned correlation/allosteric/pseudokinase
            if _has_dccm_request:
                steps.append(AnalysisStep(
                    name="Calculate Dynamic Cross-Correlation Matrix (DCCM)",
                    description=(
                        "Compute normalised DCCM of Cα fluctuations to reveal correlated "
                        "and anti-correlated residue motions. Generates dccm.csv and "
                        "dccm_heatmap.png internally."
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
                    reason=(
                        "DCCM reveals allosteric communication and correlated domain motions "
                        "— key for differentiating pseudokinase dynamics"
                    )
                ))

        if energy_name:
            steps.extend([
                AnalysisStep(
                    name="Analyze Energy",
                    description="Extract and analyze energy terms from simulation",
                    tool_name="analyze_energy",
                    tool_params={"energy_file": energy_name, "output_file": "energy.dat"},
                    reason="Energy analysis assesses simulation stability"
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
                    reason="Visualise thermodynamic equilibration"
                ),
            ])

        # Always add combined metrics panel when standard .dat files are available
        if traj_name and topo_name:
            _panel_files  = ["rmsd.dat", "rmsf.dat", "gyration.dat"]
            _panel_xl     = ["Time (ns)", "Residue",   "Time (ns)"]
            _panel_yl     = ["RMSD (Å)",  "RMSF (Å)",  "Rg (Å)"]
            _panel_titles = ["RMSD",       "RMSF",       "Radius of Gyration"]
            if energy_name:
                _panel_files.append("energy.dat")
                _panel_xl.append("Time (ns)")
                _panel_yl.append("Energy (kJ/mol)")
                _panel_titles.append("Energy")
            steps.append(AnalysisStep(
                name="Create Combined Metrics Plot",
                description=(
                    "Multi-panel summary figure of RMSD, RMSF, Rg "
                    "(and energy if available) in one PNG."
                ),
                tool_name="plot_multipanel",
                tool_params={
                    "data_files": _panel_files,
                    "output_file": "combined_metrics.png",
                    "layout": "vertical",
                    "titles": _panel_titles,
                    "xlabels": _panel_xl,
                    "ylabels": _panel_yl,
                },
                reason=(
                    "Standard combined-overview plot present in every simulation folder "
                    "for quick quality-control review."
                ),
            ))

        return AnalysisPlan(
            reasoning="Using standard MD analysis workflow (LLM fallback) with plotting",
            overview="Standard trajectory analysis: RMSD, RMSF, Rg (+ ligand pocket distance and/or DCCM if requested) with plots",
            steps=steps,
            potential_issues=["Requires trajectory and topology files"],
            recommendations=["Verify all files exist before execution"]
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
                    skip_msg = (
                        f"Skipping step {i+1} '{step.name}': '{step.tool_name}' is a "
                        "cross-simulation tool and cannot run in per-simulation analysis"
                    )
                    execution_log.append(f"\n⚠ {skip_msg}")
                    warnings.append(skip_msg)
                    log_agent_action("analysis", f"Step {i+1}/{len(plan.steps)} skipped", {
                        "step": step.name,
                        "reason": f"Combined-analysis tool not allowed: {step.tool_name}"
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
                
                # Execute tool with retry logic
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
