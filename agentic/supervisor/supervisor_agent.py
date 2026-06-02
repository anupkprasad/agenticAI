"""
Clean and Simple LLM-Powered MD Workflow Supervisor

Responsibilities:
1. Analyze PDB structure and validate components
2. Enrich user prompt ONCE with all context (Single LLM call for entire workflow)  
3. Validate input feasibility (PDB files, parameters, user intent)
4. Collaborate with planner to create execution plans
5. Route tasks to field agents in STRICT ORDER: preprocessing → simsetup → hpc → analysis → reporter
6. Multi-simulation orchestration: loop through per-sim prompts, then combined analysis + reporter
"""

import json
import logging
import shutil
import yaml
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..state import MDState
from ..utils import log_supervisor_routing, log_agent_action
from ..utils.conversation_logger import set_log_file
from ..llm import LLMClient
from ..planner import MDPlanner
from .tools import (
    parse_component_selection,
    validate_feasibility,
    detect_task_required_inputs
)

# Import PDB analyzer
from src.utils.pdb_analyzer import analyze_pdb

# Import unified enrichment
from src.supervisor.unified_enricher import enrich_prompt_unified, get_agent_execution_order

logger = logging.getLogger(__name__)


class MDSupervisor:
    """
    LLM-powered supervisor that orchestrates the MD workflow.
    
    Handles input validation, PDB analysis, planning collaboration, and agent routing.
    """

    def __init__(self, llm_client: Optional[LLMClient] = None, config_path: Optional[str] = None):
        """
        Initialize supervisor with LLM and configuration.

        Args:
            llm_client: LLMClient instance for LLM operations
            config_path: Path to config.yaml (auto-detected if None)
        """
        if llm_client is None:
            raise ValueError("llm_client is required for supervisor operation")

        self.llm = llm_client
        self.planner = None  # Lazy-load planner on first use

        # Load configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config.yaml")

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        with open(config_path, "r") as f:
            self.config = yaml.safe_load(f)

        self.supervisor_config = self.config.get("supervisor", {})
        self.agents_registry = self.config.get("agents", {})
        self.workflow_config = self.config.get("workflow", {})

        logger.info(
            f"MDSupervisor initialized with {len(self.agents_registry)} agents "
            f"from {config_path}"
        )

    def _extract_pdb_filename(self, user_goal: str) -> Optional[str]:
        """Extract PDB filename (.pdb) from user goal."""
        goal_lower = user_goal.lower()
        pdb_match = re.search(r'(\w+\.pdb)', goal_lower)
        if pdb_match:
            filename = pdb_match.group(1)
            logger.info(f"Extracted PDB filename: {filename}")
            return filename
        
        # Try explicit file pattern
        file_match = re.search(r'file\s+(?:is|:)?\s*(\w+\.pdb)', goal_lower)
        if file_match:
            return file_match.group(1)
        return None

    def supervisor_node(self, state: MDState) -> MDState:
        """
        Main supervisor routing logic with unified enrichment and strict agent ordering.

        Pipeline (regular mode):
        1. Input Validation → PDB analysis and feasibility check
        2. Unified Enrichment → SINGLE LLM call to enrich prompt
        3. Create Execution Plan → Collaborate with planner
        4. Execute Agents → Route to field agents in STRICT ORDER
        5. Generate Final Report

        Pipeline (multi-simulation mode):
        1-3. Same (enrichment of overall goal, master plan creates per-sim prompts)
        4. Per-Sim Loop → For each sim: full pipeline in {basepath}/{label}/
        5. Combined Analysis → analysis + reporter at {basepath}/ level
        6. Final Report
        """
        if self.planner is None:
            self.planner = MDPlanner(llm_client=self.llm)

        logger.info("=" * 60)
        logger.info("SUPERVISOR: Analyzing workflow state and routing decision")
        logger.info("=" * 60)

        multi_sim_phase = state.get("multi_sim_phase")

        # ── Subtask type initialisation (once) ───────────────────────────
        if not state.get("subtask_type_initialized"):
            subtask_type = state.get("subtask_type")
            if subtask_type:
                logger.info(f"SUPERVISOR: Subtask type: {subtask_type}")
                if subtask_type == "multi_agent":
                    logger.info(f"SUPERVISOR: Agent list: {state.get('agent_list', [])}")
            required_inputs = detect_task_required_inputs(subtask_type, state.get("agent_list"))
            state["required_inputs"] = required_inputs
            state["subtask_type_initialized"] = True

        # ── Debug log ─────────────────────────────────────────────────────
        has_plan = bool(state.get("execution_plan"))
        current_agent_idx = state.get("current_agent_idx", 0)
        subtask_type = state.get("subtask_type", "full_task")
        required_agents = get_agent_execution_order(subtask_type, state)
        logger.info(
            f"SUPERVISOR: plan={has_plan}, phase={multi_sim_phase}, "
            f"agent_idx={current_agent_idx}/{len(required_agents)}, "
            f"plan_executed={state.get('plan_executed')}"
        )

        # ── Per-sim or combined workflow complete ─────────────────────────
        # Must check BEFORE step 1 so that plan_executed=True routes correctly.
        if state.get("plan_executed"):
            if multi_sim_phase == "executing_sims":
                logger.info("SUPERVISOR [multi-sim]: Per-sim cycle complete — advancing")
                return self._advance_multi_sim(state)
            else:
                logger.info("SUPERVISOR: All tasks complete — final report")
                state["next_node"] = "final_report"
                log_supervisor_routing(state, "final_report", "All workflow tasks complete")
                return state

        # ── Step 1: Input validation ──────────────────────────────────────
        if not state.get("input_validated") and state.get("user_goal"):
            logger.info(f"SUPERVISOR: Routing to input validation (subtask={subtask_type})")
            state["next_node"] = "input_validation"
            return state

        # ── Step 2: Prompt enrichment (single call per sim/phase) ─────────
        if state.get("input_validated") and not state.get("enriched_prompt"):
            logger.info("SUPERVISOR: Input validated, enriching prompt")
            enriched = enrich_prompt_unified(state, self.llm, self.supervisor_config)
            state["enriched_prompt"] = enriched
            state["rephrased_goal"] = enriched
            # For multi-sim: save master prompt once so it survives per-sim state resets.
            # The combined reporter uses this to show the user's actual goal, not the
            # combined_analysis_plan dump.
            if state.get("is_multi_simulation") and not state.get("master_enriched_prompt"):
                state["master_enriched_prompt"] = enriched
            logger.info(f"SUPERVISOR: Enrichment complete ({len(enriched)} chars)")

        # ── Step 2.5: Multi-sim master planning (supervisor-side, no tools context) ─
        # Build sim_prompts + combined_analysis_plan right after enrichment and
        # before routing to the planner.  Replaces the old planner-side
        # _create_multi_sim_master_plan which exposed the full tools context to
        # the LLM unnecessarily.
        if (state.get("is_multi_simulation")
                and state.get("enriched_prompt")
                and not state.get("sim_prompts")
                and multi_sim_phase is None):
            logger.info("SUPERVISOR [multi-sim]: Building master plan (per-sim prompts + combined plan)")
            state = self._create_multi_sim_master_plan(state)
            # Fall through to the detection block below which will start the per-sim loop.

        # ── Multi-sim: master plan present (sim_prompts set, no exec plan) ─
        # Either just built above or restored from a checkpoint — start the
        # per-sim loop when we have sim_prompts but no execution_plan yet.
        if (state.get("is_multi_simulation")
                and state.get("sim_prompts")
                and not state.get("execution_plan")
                and multi_sim_phase is None):
            logger.info("SUPERVISOR [multi-sim]: Master plan ready — starting per-sim loop")
            state["multi_sim_phase"] = "executing_sims"
            state["current_sim_index"] = 0
            state["completed_sim_states"] = []
            return self._start_next_sim(state)

        # ── Step 3: Create execution plan ────────────────────────────────
        if not state.get("execution_plan") and state.get("enriched_prompt"):
            logger.info("SUPERVISOR: Routing to planner for execution plan")
            state["next_node"] = "planner"
            return state

        # ── Step 4: Extract agent-specific sub-plans ─────────────────────
        if state.get("execution_plan") and not state.get("preprocessing_instructions"):
            logger.info("SUPERVISOR: Extracting agent-specific plans")
            state = self._extract_agent_specific_plans(state)

        # ── Step 5: Assign field agents ───────────────────────────────────
        if state.get("execution_plan") and not state.get("plan_executed"):
            logger.info("SUPERVISOR: Assigning field agents")
            state = self._assign_field_agent_tasks(state)

            # "_assign_field_agent_tasks" sets next_node="supervisor" when all
            # per-sim (or combined-analysis) agents complete, to signal that the
            # multi-sim loop should advance.  But "supervisor" is not a valid
            # target in _route_from_supervisor — handle the advancement here so
            # the returned state always carries a valid next_node for LangGraph.
            if state.get("plan_executed"):
                if state.get("multi_sim_phase") == "executing_sims":
                    logger.info(
                        "SUPERVISOR [multi-sim]: Per-sim cycle complete — "
                        "advancing multi-sim loop inline"
                    )
                    return self._advance_multi_sim(state)
                # combined_analysis done (multi_sim_phase was just set to
                # "combined_reporter" by _assign_field_agent_tasks), or any
                # other case where next_node was left as "supervisor".
                if state.get("next_node") == "supervisor":
                    logger.info(
                        "SUPERVISOR: plan_executed with next_node=supervisor — "
                        "redirecting to final_report"
                    )
                    state["next_node"] = "final_report"
            return state

        # ── Fallback ──────────────────────────────────────────────────────
        if state.get("errors"):
            logger.error(f"SUPERVISOR: {len(state['errors'])} errors — final report")
        else:
            logger.info("SUPERVISOR: Workflow complete")
        state["next_node"] = "final_report"
        return state

    # ── Multi-Simulation Orchestration ───────────────────────────────────

    def _start_next_sim(self, state: MDState) -> MDState:
        """
        Reset state for the current sim_index and route to input_validation.
        Called when starting (or restarting) a per-sim pipeline.
        """
        sim_prompts = state.get("sim_prompts", [])
        current_idx = state.get("current_sim_index", 0)

        sim_info = sim_prompts[current_idx]
        sim_label = sim_info.get("label", f"sim_{current_idx}")
        sim_pdb = sim_info.get("pdb", "")
        sim_goal = sim_info.get("prompt", "")
        sim_working_dir = sim_info.get("working_dir", "")

        logger.info(
            f"SUPERVISOR [multi-sim]: Starting sim {current_idx + 1}/"
            f"{len(sim_prompts)}: {sim_label}  pdb={sim_pdb}"
        )

        # Reset per-sim state, set working_directory to {basepath}/{label}/
        state = self._reset_state_for_new_sim(state, sim_goal, sim_working_dir, sim_pdb)

        # Copy PDB into per-sim directory so validator can find it
        if sim_pdb and os.path.isfile(sim_pdb):
            dest = Path(sim_working_dir) / Path(sim_pdb).name
            if not dest.exists():
                Path(sim_working_dir).mkdir(parents=True, exist_ok=True)
                shutil.copy2(sim_pdb, dest)
                logger.info(f"Copied PDB {sim_pdb} → {dest}")
            state["user_goal"] = sim_goal.replace(sim_pdb, Path(sim_pdb).name)

        state["next_node"] = "input_validation"
        return state

    def _advance_multi_sim(self, state: MDState) -> MDState:
        """
        Save current sim state, increment index, start next sim or combined analysis.
        Called when plan_executed=True in executing_sims phase.
        """
        sim_prompts = state.get("sim_prompts", [])
        current_idx = state.get("current_sim_index", 0)

        # Save snapshot of completed sim
        self._save_sim_state(state, current_idx)
        current_idx += 1
        state["current_sim_index"] = current_idx

        logger.info(
            f"SUPERVISOR [multi-sim]: Sim {current_idx}/{len(sim_prompts)} saved"
        )

        if current_idx >= len(sim_prompts):
            # All sims complete — start combined analysis at basepath level
            logger.info("SUPERVISOR [multi-sim]: All sims complete — combined analysis")
            return self._setup_combined_analysis(state)

        # Start next sim
        return self._start_next_sim(state)

    def _setup_combined_analysis(self, state: MDState) -> MDState:
        """
        Prepare state for combined analysis at basepath level.

        After this, the regular supervisor flow handles everything:
          enrichment is skipped (enriched_prompt is set)
          planner creates a combined execution plan
          analysis and reporter agents run in {basepath}/
        """
        completed = state.get("completed_sim_states", [])

        # basepath = parent of per-sim dirs
        basepath = str(
            Path(state.get("sim_working_dirs", [state.get("working_directory", "")])[0]).parent.resolve()
        )

        logger.info(f"SUPERVISOR [multi-sim]: Combined analysis at basepath={basepath}")

        # Switch log back to basepath
        set_log_file(str(Path(basepath) / "agent_conversation.log"))

        # Build combined instructions
        sim_data_summary = self._build_sim_data_summary(completed)
        combined_plan = state.get("combined_analysis_plan", "")
        combined_instructions = (
            f"## Combined Multi-Simulation Analysis\n\n"
            f"{combined_plan}\n\n"
            f"## Simulation Data\n\n{sim_data_summary}\n\n"
            f"Save all combined plots and reports to the analysis and reporter "
            f"directories under: {basepath}"
        )

        # Preserve multi-sim bookkeeping + config
        preserved_keys = {
            "is_multi_simulation", "sim_prompts", "combined_analysis_plan",
            "sim_working_dirs", "pdb_list", "completed_sim_states",
            "md_engine", "force_field", "water_model", "human_in_loop",
            "subtask_type", "subtask_type_initialized", "agent_list",
            "required_inputs",
            # Master prompt — preserved so combined reporter shows supervisor's rephrased goal
            "master_enriched_prompt",
            # Original --goal text — shown verbatim in the combined report
            "user_goal_original",
        }
        preserved = {k: state[k] for k in preserved_keys if k in state}

        # Reset per-sim artifacts
        for key in [
            "raw_pdb", "cleaned_pdb", "preprocessing_report", "pdb_analysis",
            "pdb_summary", "component_selection", "system_info",
            "ligand_files", "ligand_resnames", "ion_files", "ion_resnames",
            "topology", "coordinates", "mdp_files", "setup_report",
            "hpc_action", "hpc_output_directory", "job_script", "job_id",
            "job_status", "trajectory_path", "energy_file", "hpc_report",
            "analysis_action", "analysis_request", "analysis_results",
            "figures", "conclusions", "analysis_directory",
            "reporter_output", "reporter_plan", "reporter_instructions",
            "reporter_file_info", "execution_plan", "plan_executed",
            "preprocessing_instructions", "setup_instructions",
            "hpc_instructions", "analysis_instructions",
            "final_report", "workflow_status",
            "file_registry", "generated_files",
            "human_feedback", "human_recommendation", "error_triggered_hitl",
        ]:
            if key in ("mdp_files", "file_registry", "generated_files", "component_selection"):
                state[key] = {}
            elif key in ("figures",):
                state[key] = []
            elif key == "plan_executed":
                state[key] = False
            elif key == "error_triggered_hitl":
                state[key] = False
            elif key == "analysis_action":
                state[key] = "full_analysis"
            else:
                state[key] = None

        state.update(preserved)

        # Set up combined analysis context
        state["multi_sim_phase"] = "combined_analysis"
        state["current_sim_index"] = len(state.get("sim_prompts", []))  # mark sims done
        state["working_directory"] = basepath
        state["user_goal"] = combined_instructions
        state["enriched_prompt"] = combined_instructions  # skip enrichment
        state["rephrased_goal"] = combined_instructions
        state["input_validated"] = True
        state["analysis_instructions"] = combined_instructions
        state["current_agent_idx"] = 0
        state["preprocess_retry_count"] = 0
        state["setup_retry_count"] = 0
        state["hpc_retry_count"] = 0
        state["analysis_retry_count"] = 0
        state["reporter_retry_count"] = 0
        state["errors"] = []
        state["warnings"] = []
        state["execution_path"] = []
        state["preprocessing_issues"] = []
        state["setup_issues"] = []

        # Ensure basepath agent dirs exist
        for sub in ("analysis", "reporter", "supervisor", "planner"):
            Path(basepath, sub).mkdir(parents=True, exist_ok=True)

        # State update preserves dir fields for combined (SecureFileManager will
        # create them at basepath level when agents run)
        state["analysis_dir"] = str(Path(basepath) / "analysis")
        state["preprocess_dir"] = str(Path(basepath) / "preprocess")
        state["simsetup_dir"] = str(Path(basepath) / "simsetup")
        state["hpc_dir"] = str(Path(basepath) / "hpc")

        # Override subtask type so only analysis + reporter agents run
        state["subtask_type"] = "analysis_only"
        state["subtask_type_initialized"] = True

        # Inject a minimal execution plan stub — bypasses the LLM planner
        # entirely.  Analysis and reporter agents detect combined_analysis mode
        # and run their deterministic combined-mode paths directly.
        state["execution_plan"] = {
            "format": "combined_analysis",
            "title": "Combined Multi-Simulation Analysis",
            "full_plan": combined_instructions,
            "agent_plans": {},
            "agent_sequence": ["analysis", "reporter"],
        }
        state["preprocessing_instructions"] = "N/A"  # skip step-4 extraction

        # Route directly to analysis — no extra supervisor round-trip needed
        state["next_node"] = "analysis"
        log_supervisor_routing(
            state, "analysis",
            f"Multi-sim combined analysis: starting for {len(completed)} sims at {basepath}"
        )
        return state

    def _handle_multi_sim_phase(self, state: MDState) -> MDState:
        """Legacy shim — delegates to the appropriate method."""
        phase = state.get("multi_sim_phase")
        if phase == "executing_sims":
            return self._start_next_sim(state)
        elif phase == "combined_analysis":
            return self._setup_combined_analysis(state)
        else:
            logger.error(f"SUPERVISOR [multi-sim]: Unknown phase '{phase}'")
            state["next_node"] = "final_report"
            return state

    def _reset_state_for_new_sim(
        self, state: MDState, new_goal: str, new_working_dir: str, raw_pdb: str
    ) -> MDState:
        """
        Reset per-simulation fields while keeping multi-sim bookkeeping.

        Preserved: is_multi_simulation, multi_sim_phase, sim_prompts,
                   combined_analysis_plan, current_sim_index,
                   completed_sim_states, sim_working_dirs, pdb_list,
                   md_engine, force_field, water_model, human_in_loop,
                   subtask_type, subtask_type_initialized, agent_list,
                   required_inputs
        """
        # Fields to keep across simulations
        preserved_keys = {
            # Multi-sim bookkeeping
            "is_multi_simulation", "multi_sim_phase", "sim_prompts",
            "combined_analysis_plan", "current_sim_index",
            "completed_sim_states", "sim_working_dirs",
            # NOTE: pdb_list and all_pdb_analyses are NOT preserved - each per-sim
            # iteration should only see its own PDB via raw_pdb, not the full list.
            # This prevents input validation from treating per-sim as multi-sim.
            # Global config
            "md_engine", "force_field", "water_model", "human_in_loop",
            "subtask_type", "subtask_type_initialized", "agent_list",
            "required_inputs",
            # Master prompt — preserved so combined reporter shows supervisor's rephrased goal
            "master_enriched_prompt",
            # Original --goal text — shown verbatim in the combined report
            "user_goal_original",
        }

        # Save values to preserve
        preserved = {k: state[k] for k in preserved_keys if k in state}

        # Reset all per-sim fields to their defaults
        state["user_goal"] = new_goal
        state["raw_pdb"] = raw_pdb if os.path.isfile(raw_pdb) else None
        state["working_directory"] = str(Path(new_working_dir).resolve())

        # Create per-sim agent directories
        wd = Path(state["working_directory"])
        wd.mkdir(parents=True, exist_ok=True)
        for subdir in ("preprocess", "simsetup", "hpc", "analysis",
                        "reporter", "supervisor", "planner", "programmer"):
            (wd / subdir).mkdir(parents=True, exist_ok=True)
        state["preprocess_dir"] = str(wd / "preprocess")
        state["simsetup_dir"] = str(wd / "simsetup")
        state["hpc_dir"] = str(wd / "hpc")
        state["analysis_dir"] = str(wd / "analysis")

        # Clear all per-sim artifacts
        per_sim_clear = [
            "enriched_prompt", "rephrased_goal", "structured_prompt",
            "input_validated", "pdb_analysis", "pdb_summary",
            "all_pdb_analyses",  # Clear multi-sim master planning data
            "component_selection", "system_info",
            "cleaned_pdb", "preprocessing_report",
            "ligand_files", "ligand_resnames", "ion_files", "ion_resnames",
            "topology", "coordinates", "mdp_files", "setup_report",
            "hpc_action", "hpc_output_directory", "job_script", "job_id",
            "job_status", "trajectory_path", "energy_file", "hpc_report",
            "analysis_action", "analysis_request", "analysis_results",
            "figures", "conclusions", "analysis_directory",
            "reporter_output", "reporter_plan", "reporter_instructions",
            "reporter_file_info",
            "execution_plan", "plan_executed",
            "preprocessing_instructions", "setup_instructions",
            "hpc_instructions", "analysis_instructions",
            "final_report", "workflow_status",
            "file_registry", "generated_files", "file_info",
            "human_feedback", "human_recommendation", "error_triggered_hitl",
        ]
        for key in per_sim_clear:
            if key in ("mdp_files",):
                state[key] = {}
            elif key in ("figures", "preprocessing_issues", "setup_issues"):
                state[key] = []
            elif key in ("file_registry", "generated_files", "component_selection"):
                state[key] = {}
            elif key in ("plan_executed",):
                state[key] = False
            elif key in ("error_triggered_hitl",):
                state[key] = False
            else:
                state[key] = None

        # Reset retry counters & agent index
        state["current_agent_idx"] = 0
        state["preprocess_retry_count"] = 0
        state["setup_retry_count"] = 0
        state["hpc_retry_count"] = 0
        state["analysis_retry_count"] = 0
        state["reporter_retry_count"] = 0
        state["execution_path"] = []
        state["errors"] = []
        state["warnings"] = []
        state["preprocessing_issues"] = []
        state["setup_issues"] = []
        state["next_node"] = None

        # Restore preserved multi-sim and global fields
        state.update(preserved)

        logger.info(
            f"SUPERVISOR [multi-sim]: State reset for new simulation "
            f"(working_dir={state['working_directory']})"
        )

        # Redirect conversation log into the per-sim directory
        sim_log = str(Path(state["working_directory"]) / "agent_conversation.log")
        set_log_file(sim_log)
        logger.info(f"SUPERVISOR [multi-sim]: Log file switched to {sim_log}")

        return state

    def _save_sim_state(self, state: MDState, sim_index: int):
        """Save a snapshot of the current per-sim state before resetting."""
        completed = state.get("completed_sim_states") or []

        # Collect the important per-sim outputs
        _errors = list(state.get("errors", []))
        # A simulation is considered successful when at least one key workflow
        # artifact was produced.  Non-fatal errors (e.g. validation warnings
        # that were recovered) do NOT mark a sim as failed.
        _success = bool(
            state.get("job_id")
            or state.get("trajectory_path")
            or state.get("topology")
            or state.get("coordinates")
            or state.get("analysis_results")
            or state.get("reporter_output")
        )
        snapshot = {
            "sim_index": sim_index,
            "label": (state.get("sim_prompts") or [{}])[sim_index].get("label", f"sim_{sim_index}"),
            "working_directory": state.get("working_directory"),
            "user_goal": state.get("user_goal"),
            "success": _success,
            "job_id": state.get("job_id"),
            "job_status": state.get("job_status"),
            "analysis_results": state.get("analysis_results", {}),
            "analysis_directory": state.get("analysis_directory") or state.get("analysis_dir"),
            "trajectory_path": state.get("trajectory_path"),
            "topology": state.get("topology"),
            "coordinates": state.get("coordinates"),
            "energy_file": state.get("energy_file"),
            "reporter_output": state.get("reporter_output"),
            "figures": list(state.get("figures", [])),
            "errors": _errors,
            "warnings": list(state.get("warnings", [])),
            "file_registry": dict(state.get("file_registry", {})),
        }

        completed.append(snapshot)
        state["completed_sim_states"] = completed

        # Also persist state.jsonl in per-sim supervisor/ directory
        try:
            sup_dir = Path(state["working_directory"]) / "supervisor"
            sup_dir.mkdir(parents=True, exist_ok=True)
            state_path = sup_dir / "state.jsonl"
            serializable = {}
            for k, v in state.items():
                try:
                    json.dumps(v, default=str)
                    serializable[k] = v
                except (TypeError, ValueError):
                    serializable[k] = str(v)
            state_path.write_text(
                json.dumps({"sim_index": sim_index, "state": serializable}, indent=2, default=str) + "\n",
                encoding="utf-8",
            )
            logger.info(f"Saved per-sim state to {state_path}")
        except Exception as e:
            logger.warning(f"Failed to save per-sim state: {e}")

    # Old combined methods removed — _setup_combined_analysis handles both analysis + reporter

    # ──────────────────────────────────────────────────────────────────────
    # Multi-simulation master planning (moved from planner — no tools context)
    # ──────────────────────────────────────────────────────────────────────

    def _create_multi_sim_master_plan(self, state: MDState) -> MDState:
        """Build per-sim prompts and combined analysis plan in the supervisor.

        Called from ``supervisor_node`` right after prompt enrichment, before
        routing to the planner.  The LLM gets the enriched goal, the PDB list,
        and the agent list but NO tools context — decomposition is purely
        goal/agent-aware, not tool-aware.
        """
        import json as _json
        import re as _re_nm
        from pathlib import Path as _Path

        enriched_prompt = state.get("enriched_prompt") or state.get("user_goal", "")
        pdb_list = state.get("pdb_list", [])
        base_working_dir = state.get("working_directory", "working_dir")
        agent_list = state.get("agent_list") or []

        if not pdb_list:
            logger.warning("SUPERVISOR [multi-sim]: No pdb_list — cannot create master plan")
            return state

        # Build per-sim working directories
        sim_working_dirs = []
        for pdb in pdb_list:
            uid = _Path(pdb).stem
            sim_dir = str((_Path(base_working_dir) / uid).resolve())
            sim_working_dirs.append(sim_dir)
        state["sim_working_dirs"] = sim_working_dirs

        # Parse protein ID → human-readable name mappings from the enriched goal
        # Matches e.g. "p24941: CDK2" or "q13418: ILK"
        _protein_name_map: Dict[str, str] = {}
        for _m in _re_nm.finditer(
            r'\b([A-Za-z0-9]{4,12})\s*:\s*([A-Za-z][A-Za-z0-9_\-]{1,30})',
            enriched_prompt,
        ):
            _k, _v = _m.group(1).lower(), _m.group(2).strip()
            # Key must contain a digit (looks like an ID) and value must start uppercase
            if any(c.isdigit() for c in _k) and _v[0].isupper():
                _protein_name_map[_k] = _v
        if _protein_name_map:
            logger.info(f"SUPERVISOR [multi-sim]: Protein name map: {_protein_name_map}")

        # Get PDB analyses for additional context
        all_pdb_analyses = state.get("all_pdb_analyses", [])
        
        # Build per-PDB context strings with system information
        pdb_context_lines = []
        for idx, pdb in enumerate(pdb_list):
            uid = _Path(pdb).stem.lower()
            prot_name = _protein_name_map.get(uid, uid.upper())
            pdb_name = _Path(pdb).name
            
            context_line = f"  {idx+1}. {pdb_name}"
            if prot_name != uid.upper():
                context_line += f" ({prot_name})"
            
            # Add system details if available from PDB analysis
            if idx < len(all_pdb_analyses):
                analysis = all_pdb_analyses[idx]
                n_atoms = analysis.get("total_atoms", 0)
                n_residues = analysis.get("total_residues", 0)
                components = analysis.get("components_available", {})
                
                comp_desc = []
                if components.get("protein"):
                    comp_desc.append("protein")
                if components.get("ligand"):
                    ligands = analysis.get("ligand", {}).get("residue_names", [])
                    if ligands:
                        comp_desc.append(f"ligand({','.join(ligands[:2])})")
                    else:
                        comp_desc.append("ligand")
                if components.get("ions"):
                    comp_desc.append("ions")
                
                if n_atoms > 0:
                    context_line += f" — {n_atoms} atoms, {', '.join(comp_desc)}"
            
            pdb_context_lines.append(context_line)

        # Describe which agents will run (from --subtask / agent_list)
        agents_desc = (
            " → ".join(agent_list) if agent_list
            else (state.get("subtask_type") or "full pipeline")
        )

        _name_map_lines = ""
        if _protein_name_map:
            _name_map_lines = (
                "PROTEIN MAPPINGS:\n"
                + "\n".join(f"  {uid}: {name}" for uid, name in _protein_name_map.items())
                + "\n\n"
            )

        decomposition_prompt = (
            f"You are an expert MD simulation planner creating NATURAL, VARIED per-simulation goals.\n\n"
            f"OVERALL PROJECT:\n{enriched_prompt}\n\n"
            f"SIMULATIONS ({len(pdb_list)}):\n"
            + "\n".join(pdb_context_lines)
            + "\n\n"
            + _name_map_lines
            + f"WORKFLOW PIPELINE: {agents_desc}\n\n"
            "TASK: Create a JSON object with two keys:\n\n"
            f'1. "sim_prompts": List of {len(pdb_list)} DISTINCT, NATURAL-LANGUAGE goals—one per simulation.\n'
            "   REQUIREMENTS:\n"
            "   • Use protein names (not IDs) when available\n"
            "   • Write each goal with VARIED phrasing—avoid repetitive templates\n"
            "   • Make goals self-contained (don't reference other proteins)\n"
            "   • Include system-specific details (ligands, ions, atom counts)\n"
            f"   • Mention ONLY the workflow steps: {agents_desc}\n"
            "   • Keep each goal concise (2-4 sentences)\n\n"
            '2. "combined_analysis_plan": Multi-paragraph string describing cross-simulation\n'
            "   analysis AFTER all individual workflows complete (comparative plots,\n"
            "   statistical summaries, PCA, markdown report).\n\n"
            "EXAMPLES of GOOD sim_prompts (varied and natural):\n"
            '  ["For the KAPCA structure with ATP and Mg²⁺, preprocess to isolate...",\n'
            '   "Process CDK2 (p24941.pdb): extract the protein-ligand complex...",\n'
            '   "Prepare MK01 for simulation by running preprocessing and setup..."]\n\n'
            "EXAMPLES of BAD sim_prompts (too repetitive):\n"
            '  ["For X, run preprocess...", "For Y, run preprocess...", "For Z, run preprocess..."]\n\n'
            "Return ONLY valid JSON, no markdown formatting or explanations."
        )

        sim_prompts_list = None
        combined_plan = None
        try:
            response = self.llm.prompt(decomposition_prompt, temperature=0.4, max_tokens=3000)
            from ..utils import log_llm_interaction
            log_llm_interaction("supervisor.multi_sim_master", decomposition_prompt, response)
            parsed = self._extract_json_from_response(response)
            if parsed and "sim_prompts" in parsed:
                sim_prompts_list = parsed["sim_prompts"]
                combined_plan = parsed.get("combined_analysis_plan", "")
                logger.info(
                    f"SUPERVISOR [multi-sim]: LLM generated {len(sim_prompts_list)} per-sim prompts"
                )
        except Exception as e:
            logger.warning(f"SUPERVISOR [multi-sim]: LLM decomposition failed: {e}")

        # Fallback: deterministic split
        if not sim_prompts_list or len(sim_prompts_list) != len(pdb_list):
            logger.info("SUPERVISOR [multi-sim]: Using deterministic prompt decomposition")
            sim_prompts_list = []
            for pdb in pdb_list:
                uid = _Path(pdb).stem.lower()
                prot_name = _protein_name_map.get(uid, "")
                pdb_name = _Path(pdb).name
                per_sim = enriched_prompt
                for other in pdb_list:
                    if other != pdb:
                        per_sim = per_sim.replace(_Path(other).name, "").replace(other, "")
                if pdb_name not in per_sim:
                    prefix = (
                        f"Process {prot_name} ({pdb_name})." if prot_name
                        else f"Process {pdb_name}."
                    )
                    per_sim = prefix + " " + per_sim
                elif prot_name and prot_name not in per_sim:
                    per_sim = f"Protein: {prot_name}. " + per_sim
                sim_prompts_list.append(per_sim.strip())
            combined_plan = (
                "Perform combined cross-simulation analysis:\n"
                "1. Comparative overlay plots (RMSD, RMSF, Rg).\n"
                "2. Statistical summary table (mean, std, min, max).\n"
                "3. Cross-simulation PCA on C-alpha coordinates if trajectories available.\n"
                "4. Markdown narrative report with per-sim highlights and cross-simulation trends."
            )

        # Build structured sim_prompts with protein-name labels
        sim_prompts = []
        for i, (pdb, prompt_text) in enumerate(zip(pdb_list, sim_prompts_list)):
            uid = _Path(pdb).stem
            label = _protein_name_map.get(uid.lower(), uid)
            sim_prompts.append({
                "pdb": str(_Path(pdb).resolve()) if _Path(pdb).exists() else pdb,
                "label": label,
                "prompt": prompt_text,
                "working_dir": sim_working_dirs[i],
            })

        state["sim_prompts"] = sim_prompts
        state["combined_analysis_plan"] = combined_plan

        logger.info(
            f"SUPERVISOR [multi-sim]: Master plan ready — {len(sim_prompts)} simulations, "
            f"labels: {[s['label'] for s in sim_prompts]}"
        )
        log_agent_action(
            agent_name="supervisor",
            action="Generated Multi-Simulation Master Plan",
            details={
                "num_simulations": len(sim_prompts),
                "labels": [s["label"] for s in sim_prompts],
                "agents": agents_desc,
                "combined_plan_preview": (combined_plan or "")[:300],
            },
        )
        return state

    def _extract_json_from_response(self, response: str) -> Optional[Dict[str, Any]]:
        """Extract the first JSON object from an LLM response using brace counting."""
        import json as _json

        start = response.find("{")
        if start == -1:
            return None
        depth = 0
        for i, ch in enumerate(response[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return _json.loads(response[start : i + 1])
                    except _json.JSONDecodeError:
                        return None
        return None

    def _build_sim_data_summary(self, completed_sims: List[Dict[str, Any]]) -> str:
        """Build a text summary of all completed simulation data paths for LLM context."""
        lines = []
        for sim in completed_sims:
            label = sim.get("label", "unknown")
            wd = sim.get("working_directory", "?")
            analysis_dir = sim.get("analysis_directory", "?")
            traj = sim.get("trajectory_path", "N/A")
            topo = sim.get("topology", "N/A")
            energy = sim.get("energy_file", "N/A")
            n_figs = len(sim.get("figures", []))
            n_errors = len(sim.get("errors", []))
            lines.append(
                f"### Simulation: {label}\n"
                f"- Working directory: {wd}\n"
                f"- Analysis directory: {analysis_dir}\n"
                f"- Trajectory: {traj}\n"
                f"- Topology: {topo}\n"
                f"- Energy: {energy}\n"
                f"- Figures generated: {n_figs}\n"
                f"- Errors: {n_errors}\n"
            )
        return "\n".join(lines)

    def input_validation_node(self, state: MDState) -> MDState:
        """
        Universal input validation node for all task types.
        
        Uses the unified validate_and_enrich_inputs() function from tools.py
        to handle both PDB-based tasks and analysis-only tasks.
        """
        from .tools import validate_and_enrich_inputs
        
        subtask_type = state.get("subtask_type", "full_task")
        
        log_agent_action(
            agent_name="supervisor.input_validation",
            action=f"Starting Unified Input Validation ({subtask_type})",
            details={
                "user_goal": state.get("user_goal", "")[:200],
                "task_type": subtask_type
            }
        )
        
        # Call unified validation function for all task types
        state = validate_and_enrich_inputs(
            state=state,
            subtask_type=subtask_type,
            llm_client=self.llm,
            config=self.supervisor_config,
            analyze_pdb_tool=analyze_pdb,
            logger=logger
        )
        
        log_supervisor_routing(
            state, "supervisor",
            f"Input validation complete for {subtask_type}, returning to supervisor for planning"
        )
        
        return state

    def _extract_agent_specific_plans(self, state: MDState) -> MDState:
        """
        Extract agent-specific instructions from the full execution plan.
        
        Prefers the pre-extracted `agent_plans` dict from the planner (deterministic).
        Falls back to regex extraction from full_plan prose if dict is unavailable.
        """
        import re
        
        execution_plan = state.get("execution_plan", {})
        agent_plans = execution_plan.get("agent_plans", {})
        full_plan = execution_plan.get("full_plan", "")
        
        if not full_plan and not agent_plans:
            logger.warning("No full_plan or agent_plans found in execution_plan, skipping extraction")
            return state
        
        # Map from agent_plans keys to state keys
        _agent_to_state = {
            "preprocessing_agent": "preprocessing_instructions",
            "setup_agent": "setup_instructions",
            "hpc_agent": "hpc_instructions",
            "analysis_agent": "analysis_instructions",
            "reporter_agent": "reporter_instructions",
        }
        
        # Strategy 1: Use pre-extracted agent_plans dict from planner (preferred)
        if agent_plans:
            logger.info(f"Using pre-extracted agent_plans from planner: {list(agent_plans.keys())}")
            for agent_key, instructions in agent_plans.items():
                state_key = _agent_to_state.get(agent_key)
                if state_key and instructions:
                    state[state_key] = instructions
                    logger.info(f"Set {state_key} from agent_plans ({len(instructions)} chars)")
            
            logger.info(
                f"Agent-specific extraction complete (from agent_plans). Keys set: "
                f"{[sk for sk in _agent_to_state.values() if state.get(sk)]}"
            )
            return state
        
        # Strategy 2: Fallback to regex extraction from full_plan prose
        logger.info(f"No agent_plans dict found, falling back to regex extraction from {len(full_plan)} char plan")
        
        # Define agent mappings: (state_key, agent_names_to_search)
        agent_mappings = {
            "preprocessing_instructions": [
                "Preprocessing Agent",
                "PDB Preprocessing Agent", 
                "Preprocess Agent"
            ],
            "setup_instructions": [
                "Simulation Setup Agent",
                "SimSetup Agent",
                "Setup Agent"
            ],
            "hpc_instructions": [
                "HPC Agent",
                "HPC Submission Agent",
                "Job Submission Agent"
            ],
            "analysis_instructions": [
                "Analysis Agent",
                "MD Analysis Agent",
                "Trajectory Analysis Agent"
            ],
            "reporter_instructions": [
                "Reporter Agent",
                "Report Generation Agent",
                "Scientific Reporter Agent"
            ]
        }
        
        # Extract instructions for each agent
        for state_key, agent_names in agent_mappings.items():
            extracted = None
            
            # Try each agent name variant
            for agent_name in agent_names:
                # Try multiple heading patterns (all anchored to line start)
                patterns = [
                    # Bold header with colon: **Agent Name:** (at line start)
                    rf'^\*\*{re.escape(agent_name)}(?:\s*:?\s*\*\*|:\*\*)\s*\n(.*?)(?=^\*\*[A-Z]|\Z)',
                    # Markdown ### heading
                    rf'^###\s*{re.escape(agent_name)}.*?\n(.*?)(?=^###|\Z)',
                    # Markdown ## heading  
                    rf'^##\s*{re.escape(agent_name)}.*?\n(.*?)(?=^##|\Z)',
                    # Numbered section: 1. **Agent Name** (at line start)
                    rf'^\d+\.\s*\*\*{re.escape(agent_name)}\*\*.*?\n(.*?)(?=^\d+\.\s*\*\*|^\*\*[A-Z]|\Z)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE | re.MULTILINE)
                    if match:
                        instructions = match.group(1).strip()
                        if len(instructions) > 50:  # Ensure substantial content
                            extracted = instructions
                            logger.info(
                                f"Extracted {len(instructions)} chars for {state_key} "
                                f"using agent name '{agent_name}'"
                            )
                            break
                
                if extracted:
                    break
            
            # Store extracted instructions (or fallback to full plan)
            if extracted:
                state[state_key] = extracted
            else:
                # Fallback: provide full plan so agent has context
                logger.warning(
                    f"Could not extract specific section for {state_key}, "
                    f"agent will receive full plan as fallback"
                )
                state[state_key] = full_plan
        
        logger.info(
            f"Agent-specific extraction complete. Keys set: "
            f"{[k for k in agent_mappings.keys() if state.get(k)]}"
        )
        
        return state

    def _assign_field_agent_tasks(self, state: MDState) -> MDState:
        """
        Route to appropriate field agents using STRICT EXECUTION ORDER.
        
        Order is ALWAYS: preprocessing → simsetup → hpc → analysis → reporter
        Agents are skipped based on:
        - Task type (e.g., analysis_only skips preprocessing/simsetup/hpc)
        - User exclusions (e.g., "no hpc")
        - Already completed work (e.g., cleaned_pdb exists)
        
        This enforces predictable, sequential execution regardless of plan.
        """
        logger.info("FIELD_AGENT_ASSIGNMENT: Using strict agent execution order")
        
        # Get the required agents in strict order for this task
        subtask_type = state.get("subtask_type", "full_task")
        required_agents = get_agent_execution_order(subtask_type, state)
        
        logger.info(f"FIELD_AGENT_ASSIGNMENT: Required agents for {subtask_type}: {required_agents}")
        
        # Get progress - which agent are we on?
        current_agent_idx = state.get("current_agent_idx", 0)
        
        if current_agent_idx >= len(required_agents):
            # All agents complete
            logger.info("FIELD_AGENT_ASSIGNMENT: All required agents completed")
            state["plan_executed"] = True

            # Multi-sim: return to supervisor to advance to next sim or combined phase
            if state.get("is_multi_simulation") and state.get("multi_sim_phase") == "executing_sims":
                logger.info("FIELD_AGENT_ASSIGNMENT: Per-sim cycle done — returning to multi-sim loop")
                state["next_node"] = "supervisor"
                return state

            # Multi-sim combined phases: transition to next phase
            if state.get("multi_sim_phase") == "combined_analysis":
                logger.info("FIELD_AGENT_ASSIGNMENT: Combined analysis done — transitioning to combined reporter")
                state["multi_sim_phase"] = "combined_reporter"
                state["next_node"] = "supervisor"
                return state

            if state.get("multi_sim_phase") == "combined_reporter":
                logger.info("FIELD_AGENT_ASSIGNMENT: Combined reporter done — going to final report")
                state["next_node"] = "final_report"
                log_supervisor_routing(state, "final_report", "Multi-sim workflow complete")
                return state

            state["next_node"] = "final_report"
            log_supervisor_routing(state, "final_report", "All workflow tasks complete")
            return state
        
        # Get the current agent to execute
        current_agent = required_agents[current_agent_idx]
        logger.info(f"FIELD_AGENT_ASSIGNMENT: Executing agent {current_agent_idx + 1}/{len(required_agents)}: {current_agent}")
        
        # Execute based on agent type with completion checks
        if current_agent == "preprocessing":
            if state.get("cleaned_pdb"):
                logger.info("FIELD_AGENT_ASSIGNMENT: Preprocessing already complete, moving to next agent")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check retry limit
            retry_count = state.get("preprocess_retry_count", 0)
            if retry_count >= 3:
                state["errors"].append("Preprocessing failed after 3 retries")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            state["next_node"] = "preprocess"
            state["preprocess_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to preprocessing")
            log_supervisor_routing(state, "preprocess", "Executing preprocessing agent")
            return state
        
        elif current_agent == "simsetup":
            if state.get("coordinates"):
                logger.info("FIELD_AGENT_ASSIGNMENT: SimSetup already complete, moving to next agent")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check retry limit
            retry_count = state.get("setup_retry_count", 0)
            if retry_count >= 3:
                state["errors"].append("SimSetup failed after 3 retries — skipping HPC submission")
                state["next_node"] = "final_report"
                logger.warning("SimSetup exhausted 3 retries — aborting workflow (no HPC submission)")
                log_supervisor_routing(state, "final_report", "SimSetup failed after 3 retries, skipping HPC")
                return state
            
            state["next_node"] = "setup"
            state["setup_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to simsetup")
            log_supervisor_routing(state, "setup", "Executing simsetup agent")
            return state
        
        elif current_agent == "hpc":
            # Check for user exclusion
            user_goal = state.get("user_goal", "").lower()
            rephrased_goal = state.get("rephrased_goal", "").lower()
            combined_goals = f"{user_goal} {rephrased_goal}"
            
            # Only skip HPC if the user EXPLICITLY excludes it.
            # Use user_goal only (not rephrased_goal) to avoid false positives
            # from enricher phrases like "No simulation execution is performed".
            user_excluded_hpc = any(phrase in user_goal for phrase in [
                "no hpc", "skip hpc", "do not submit", "don't submit",
                "without hpc", "local only"
            ])
            
            if user_excluded_hpc:
                logger.info("FIELD_AGENT_ASSIGNMENT: User excluded HPC, skipping")
                state["warnings"].append("HPC execution skipped per user request")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            if state.get("job_id"):
                logger.info("FIELD_AGENT_ASSIGNMENT: HPC already complete, moving to next agent")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # HPC gets only 1 attempt (no retries)
            retry_count = state.get("hpc_retry_count", 0)
            if retry_count >= 1:
                state["errors"].append("HPC execution failed (no retries)")
                state["warnings"].append("HPC simulation not submitted due to failure")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            state["next_node"] = "hpc"
            state["hpc_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to HPC (attempt 1/1)")
            log_supervisor_routing(state, "hpc", "Executing HPC agent")
            return state
        
        elif current_agent == "analysis":
            if state.get("analysis_results"):
                logger.info("FIELD_AGENT_ASSIGNMENT: Analysis already complete, moving to next agent")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check retry limit
            retry_count = state.get("analysis_retry_count", 0)
            if retry_count >= 3:
                state["errors"].append("Analysis failed after 3 retries")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            state["next_node"] = "analysis"
            state["analysis_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to analysis")
            log_supervisor_routing(state, "analysis", "Executing analysis agent")
            return state
        
        elif current_agent == "reporter":
            if state.get("reporter_output"):
                logger.info("FIELD_AGENT_ASSIGNMENT: Reporter already complete, moving to next agent")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check retry limit
            retry_count = state.get("reporter_retry_count", 0)
            if retry_count >= 2:
                state["errors"].append("Reporter failed after 2 retries")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
            state["next_node"] = "reporter"
            state["reporter_retry_count"] = retry_count + 1
            logger.info("FIELD_AGENT_ASSIGNMENT: Routing to reporter")
            log_supervisor_routing(state, "reporter", "Executing reporter agent")
            return state
        
        else:
            # Unknown agent (shouldn't happen with get_agent_execution_order)
            error_msg = f"Unknown agent '{current_agent}' in execution order"
            logger.error(f"FIELD_AGENT_ASSIGNMENT: {error_msg}")
            state["errors"].append(error_msg)
            state["next_node"] = "final_report"
            return state

    def get_agents_summary(self) -> str:
        """Build summary of available agents for LLM context."""
        summary = []
        for agent_id, config in self.agents_registry.items():
            summary.append(
                f"\n{agent_id.upper()}:\n"
                f"  - Name: {config.get('name', 'N/A')}\n"
                f"  - Purpose: {config.get('description', 'N/A')}\n"
                f"  - Capabilities: {', '.join(config.get('capabilities', []))}\n"
                f"  - Requires: {', '.join(config.get('input_requirements', []))}\n"
                f"  - Produces: {', '.join(config.get('output_provides', []))}"
            )
        return "".join(summary)

    def get_workflow_progress(self, state: MDState) -> str:
        """Get human-readable workflow progress summary."""
        completed = []

        if state.get("raw_pdb"):
            completed.append("input_validation")
        if state.get("execution_plan"):
            completed.append("planning")
        if state.get("cleaned_pdb"):
            completed.append("preprocessing")
        if state.get("coordinates"):
            completed.append("setup")
        if state.get("job_id"):
            completed.append("hpc")
        if state.get("analysis_results"):
            completed.append("analysis")
        if state.get("reporter_output"):
            completed.append("reporter")

        total = len(self.workflow_config.get("default_pipeline", []))
        progress = (len(completed) / (total + 2)) * 100
        return f"Progress: {completed} ({progress:.0f}%)"
