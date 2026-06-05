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
from ..utils.plan_persistence import save_plan_artifacts
from ..utils.conversation_logger import set_log_file
from ..llm import LLMClient
from ..planner import MDPlanner
from .tools import (
    parse_component_selection,
    validate_feasibility,
    detect_task_required_inputs,
)
from src.supervisor.component_parser import (
    parse_sim_case_requirements,
    validate_sim_case_components,
)

# Import PDB analyzer
from src.utils.pdb_analyzer import analyze_pdb

# Import unified enrichment
from src.supervisor.unified_enricher import enrich_prompt_unified, get_agent_execution_order

logger = logging.getLogger(__name__)


def _coerce_plan_text(value: Any, default: str = "") -> str:
    """Normalize LLM plan fields (str, list, or dict) to a markdown-safe string."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, list):
        parts = [_coerce_plan_text(item, default="") for item in value]
        parts = [p for p in parts if p]
        return "\n".join(parts) if parts else default
    if isinstance(value, dict):
        for key in ("prompt", "goal", "text", "description", "plan"):
            if key in value and value[key]:
                return _coerce_plan_text(value[key], default=default)
        return json.dumps(value, indent=2, default=str)
    return str(value).strip() or default


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
        if not state.get("multi_sim_base_dir"):
            state["multi_sim_base_dir"] = state.get("working_directory")

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
        pdb_name = Path(sim_pdb).name if sim_pdb else ""
        resolved_pdb = sim_pdb
        if sim_pdb:
            dest = Path(sim_working_dir) / pdb_name
            if os.path.isfile(sim_pdb):
                if not dest.exists():
                    Path(sim_working_dir).mkdir(parents=True, exist_ok=True)
                    shutil.copy2(sim_pdb, dest)
                    logger.info(f"Copied PDB {sim_pdb} → {dest}")
                resolved_pdb = str(dest)
            else:
                # Try shared copy at multi-sim base directory
                base_dir = state.get("multi_sim_base_dir") or state.get("working_directory")
                base_candidate = Path(base_dir) / pdb_name
                if base_candidate.is_file():
                    Path(sim_working_dir).mkdir(parents=True, exist_ok=True)
                    shutil.copy2(base_candidate, dest)
                    resolved_pdb = str(dest)
                    logger.info(f"Copied shared PDB {base_candidate} → {dest}")

            state["raw_pdb"] = resolved_pdb if os.path.isfile(resolved_pdb) else None
            state["user_goal"] = sim_goal.replace(sim_pdb, pdb_name)

        # Propagate per-structure download metadata for preprocess agent
        structure_requests = state.get("structure_requests") or {}
        uid_key = Path(sim_pdb).stem.lower() if sim_pdb else ""
        if uid_key in structure_requests:
            state["structure_request"] = structure_requests[uid_key]
        elif state.get("structure_request"):
            pass  # keep master-level request
        elif uid_key:
            state["structure_request"] = {
                "uniprot_id": uid_key.upper(),
                "needs_download": not bool(state.get("raw_pdb")),
                "structure_source": "auto",
            }

        state["sim_case"] = {
            "label": sim_label,
            "case_id": sim_info.get("case_id"),
            "case_description": sim_info.get("case_description"),
            "case_directive": sim_info.get("case_directive"),
        }

        skipped = self._validate_and_maybe_skip_sim_case(state, sim_pdb, sim_goal)
        if skipped:
            return skipped

        state["next_node"] = "input_validation"
        return state

    def _validate_and_maybe_skip_sim_case(
        self,
        state: MDState,
        sim_pdb: str,
        sim_goal: str,
    ) -> Optional[MDState]:
        """
        Skip holo/component-specific simulations when required ligands/ions
        are absent from the source structure (e.g. AlphaFold protein-only PDB).
        """
        sim_case = state.get("sim_case") or {}
        requirements = parse_sim_case_requirements(
            label=sim_case.get("label", ""),
            case_description=sim_case.get("case_description", ""),
            case_directive=sim_case.get("case_directive", ""),
            user_goal=sim_goal,
        )
        if requirements.get("case_type") in ("default", "protein_only"):
            return None

        source_pdb = sim_pdb
        if source_pdb and not os.path.isfile(source_pdb):
            base_dir = state.get("multi_sim_base_dir") or state.get("working_directory")
            candidate = Path(base_dir) / Path(source_pdb).name
            if candidate.is_file():
                source_pdb = str(candidate)

        if not source_pdb or not os.path.isfile(source_pdb):
            return None

        analysis_result = analyze_pdb.invoke({"pdb_file": source_pdb})
        if not analysis_result.get("success"):
            return None

        validation = validate_sim_case_components(
            analysis_result.get("analysis", {}),
            requirements,
        )
        if validation.get("is_feasible"):
            return None

        label = sim_case.get("label", "simulation")
        for err in validation.get("errors", []):
            msg = f"Skipping {label}: {err}"
            state["errors"].append(msg)
            state["warnings"].append(msg)
            logger.error(msg)

        return self._skip_current_sim(state, reason="; ".join(validation.get("errors", [])))

    def _skip_current_sim(self, state: MDState, reason: str) -> MDState:
        """Record a failed sim snapshot and advance to the next simulation."""
        sim_prompts = state.get("sim_prompts", [])
        current_idx = state.get("current_sim_index", 0)
        sim_label = (state.get("sim_case") or {}).get("label", f"sim_{current_idx}")

        sim_case = state.get("sim_case") or {}
        snapshot = {
            "sim_index": current_idx,
            "label": sim_label,
            "case_description": sim_case.get("case_description"),
            "working_directory": state.get("working_directory"),
            "user_goal": state.get("user_goal"),
            "success": False,
            "skipped": True,
            "skip_reason": reason,
            "errors": list(state.get("errors", [])),
            "warnings": list(state.get("warnings", [])),
        }
        completed = list(state.get("completed_sim_states") or [])
        completed.append(snapshot)
        state["completed_sim_states"] = completed

        current_idx += 1
        state["current_sim_index"] = current_idx
        logger.warning(
            "SUPERVISOR [multi-sim]: Skipped sim %s (%s)",
            sim_label,
            reason,
        )

        if current_idx >= len(sim_prompts):
            return self._setup_combined_analysis(state)
        return self._start_next_sim(state)

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
            "multi_sim_base_dir",
            "structure_requests",
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
            "sim_case",
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
        sim_case = state.get("sim_case") or {}
        snapshot = {
            "sim_index": sim_index,
            "label": (state.get("sim_prompts") or [{}])[sim_index].get("label", f"sim_{sim_index}"),
            "case_description": sim_case.get("case_description"),
            "working_directory": state.get("working_directory"),
            "user_goal": state.get("user_goal"),
            "success": _success,
            "skipped": False,
            "job_id": state.get("job_id"),
            "job_script": state.get("job_script"),
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

    def _detect_component_cases(self, prompt: str) -> List[Dict[str, str]]:
        """Infer component-specific simulation cases from user goal text."""
        p = (prompt or "").lower()
        # Normalize common unicode variants from LLM responses.
        p = (
            p.replace("\u2011", "-")
            .replace("\u2012", "-")
            .replace("\u2013", "-")
            .replace("\u2014", "-")
            .replace("\u2212", "-")
        )

        has_protein_only = bool(re.search(r"\bprotein[\s\-]*(only|alone)\b", p))
        has_atp = "atp" in p
        has_holo = "holo" in p
        has_mg = bool(re.search(r"\bmg(?:2\+?|\u00b2\+?)?\b", p))
        has_case_language = bool(
            re.search(
                r"two\s+different\s+cases?|two\s+systems\s+per\s+file|"
                r"case\s*[:\-]|\bcase\s*1\b|\bcase\s*2\b|"
                r"\(\s*1\s*\)|\(\s*2\s*\)|\b1\.\b|\b2\.\b",
                p,
            )
        )

        # Common request pattern: same PDB run in multiple component conditions.
        if has_case_language and has_protein_only and (has_atp or has_holo):
            full_suffix = "ATP_MG" if has_mg else "ATP"
            full_desc = "protein + ATP + MG" if has_mg else "protein + ATP"
            full_directive = (
                "Keep protein with ATP ligand and Mg ions from the source PDB."
                if has_mg else
                "Keep protein with ATP ligand from the source PDB."
            )
            return [
                {
                    "case_id": "protein_only",
                    "suffix": "",
                    "description": "protein only",
                    "directive": "Use protein-only system. Remove ATP, ligands, and non-essential ions.",
                },
                {
                    "case_id": "protein_with_ligand",
                    "suffix": full_suffix,
                    "description": full_desc,
                    "directive": full_directive,
                },
            ]

        # Default behavior: one simulation per PDB using full detected system.
        return [
            {
                "case_id": "default",
                "suffix": "",
                "description": "default system from input PDB",
                "directive": "Use the full biologically relevant system present in the input PDB.",
            }
        ]

    def _create_multi_sim_master_plan(self, state: MDState) -> MDState:
        """Build per-sim prompts and combined analysis plan in the supervisor.

        Called from ``supervisor_node`` right after prompt enrichment, before
        routing to the planner. The master plan can expand each PDB into
        multiple component-specific simulations (for example protein-only and
        protein+ATP+MG), each with its own directory and prompt.
        """
        import re as _re_nm
        from pathlib import Path as _Path

        enriched_prompt = state.get("enriched_prompt") or state.get("user_goal", "")
        pdb_list = state.get("pdb_list", [])
        base_working_dir = state.get("working_directory", "working_dir")
        agent_list = state.get("agent_list") or []

        if not pdb_list:
            logger.warning("SUPERVISOR [multi-sim]: No pdb_list - cannot create master plan")
            return state

        # Parse protein ID -> human-readable name mappings from goal text.
        _protein_name_map: Dict[str, str] = {}
        for _m in _re_nm.finditer(
            r'\b([A-Za-z0-9]{4,12})\s*:\s*([A-Za-z][A-Za-z0-9_\-]{1,30})',
            enriched_prompt,
        ):
            _k, _v = _m.group(1).lower(), _m.group(2).strip()
            if any(c.isdigit() for c in _k) and _v[0].isupper():
                _protein_name_map[_k] = _v
        if _protein_name_map:
            logger.info(f"SUPERVISOR [multi-sim]: Protein name map: {_protein_name_map}")

        # Expand each PDB into one or more component-specific simulation cases.
        component_cases = self._detect_component_cases(enriched_prompt)
        expanded_entries: List[Dict[str, Any]] = []
        for pdb in pdb_list:
            uid = _Path(pdb).stem
            uid_l = uid.lower()
            prot_name = _protein_name_map.get(uid_l, uid.upper())
            for case in component_cases:
                suffix = case.get("suffix", "")
                sim_label = f"{uid}_{suffix}" if suffix else uid
                sim_dir = str((_Path(base_working_dir) / sim_label).resolve())
                expanded_entries.append(
                    {
                        "pdb": pdb,
                        "uid": uid,
                        "protein_name": prot_name,
                        "label": sim_label,
                        "working_dir": sim_dir,
                        "case_description": case.get("description", "default system"),
                        "case_directive": case.get("directive", "Use full system from PDB."),
                    }
                )

        state["sim_working_dirs"] = [e["working_dir"] for e in expanded_entries]

        # Build simulation context lines.
        all_pdb_analyses = state.get("all_pdb_analyses", [])
        pdb_analysis_map: Dict[str, Dict[str, Any]] = {}
        for idx, pdb in enumerate(pdb_list):
            if idx < len(all_pdb_analyses):
                pdb_analysis_map[_Path(pdb).name] = all_pdb_analyses[idx]

        sim_context_lines: List[str] = []
        for i, e in enumerate(expanded_entries, 1):
            pdb_name = _Path(e["pdb"]).name
            line = (
                f"  {i}. label={e['label']} | source={pdb_name} | "
                f"case={e['case_description']} | dir={e['working_dir']}"
            )
            analysis = pdb_analysis_map.get(pdb_name)
            if analysis:
                n_atoms = analysis.get("total_atoms", 0)
                comps = analysis.get("components_available", {})
                comp_desc = []
                if comps.get("protein"):
                    comp_desc.append("protein")
                if comps.get("ligand"):
                    ligands = analysis.get("ligand", {}).get("residue_names", [])
                    comp_desc.append(f"ligand({','.join(ligands[:2])})" if ligands else "ligand")
                if comps.get("ions"):
                    comp_desc.append("ions")
                if n_atoms:
                    line += f" | source_components={','.join(comp_desc)} | atoms={n_atoms}"
            sim_context_lines.append(line)

        agents_desc = (
            " -> ".join(agent_list) if agent_list
            else (state.get("subtask_type") or "full pipeline")
        )

        name_map_lines = ""
        if _protein_name_map:
            name_map_lines = (
                "PROTEIN MAPPINGS:\n"
                + "\n".join(f"  {uid}: {name}" for uid, name in _protein_name_map.items())
                + "\n\n"
            )

        decomposition_prompt = (
            "You are an expert MD simulation planner creating natural, varied per-simulation goals.\n\n"
            f"OVERALL PROJECT:\n{enriched_prompt}\n\n"
            f"SIMULATION ENTRIES ({len(expanded_entries)} total):\n"
            + "\n".join(sim_context_lines)
            + "\n\n"
            + name_map_lines
            + f"WORKFLOW PIPELINE: {agents_desc}\n\n"
            "TASK: Return JSON with keys:\n"
            f"1) sim_prompts: list of {len(expanded_entries)} prompts, same order as entries.\n"
            "2) combined_analysis_plan: comparative analysis plan across all entries.\n\n"
            "Prompt requirements:\n"
            "- Mention source PDB and target label directory context.\n"
            "- Enforce the case objective (for example protein only vs protein+ATP+MG).\n"
            "- Keep each prompt concise and not repetitive.\n"
            f"- Mention only these workflow steps: {agents_desc}.\n\n"
            "Return only valid JSON."
        )

        sim_prompts_list = None
        combined_plan = None
        try:
            response = self.llm.prompt(decomposition_prompt, temperature=0.4, max_tokens=3200)
            from ..utils import log_llm_interaction
            log_llm_interaction("supervisor.multi_sim_master", decomposition_prompt, response)
            parsed = self._extract_json_from_response(response)
            if parsed and "sim_prompts" in parsed:
                sim_prompts_list = [
                    _coerce_plan_text(item, default="")
                    for item in parsed["sim_prompts"]
                ]
                combined_plan = _coerce_plan_text(
                    parsed.get("combined_analysis_plan", ""),
                    default="",
                )
                logger.info(
                    f"SUPERVISOR [multi-sim]: LLM generated {len(sim_prompts_list)} per-sim prompts"
                )

                # Detect near-template outputs (same sentence with only path/PDB swapped).
                if len(sim_prompts_list) > 1:
                    _keys = []
                    for _txt in sim_prompts_list:
                        _k = (_coerce_plan_text(_txt) or "").lower()
                        _k = re.sub(r"/[\w./\-]+", "<path>", _k)
                        _k = re.sub(r"\b[\w\-]+\.pdb\b", "<pdb>", _k)
                        _k = re.sub(r"\b[a-z0-9]{4,12}\b", "<tok>", _k)
                        _k = re.sub(r"\b\d+\s*ns\b", "<time>", _k)
                        _k = re.sub(r"\s+", " ", _k).strip()
                        _keys.append(_k)
                    if len(set(_keys)) <= max(1, len(_keys) // 3):
                        logger.warning(
                            "SUPERVISOR [multi-sim]: LLM sim_prompts are repetitive; "
                            "switching to deterministic per-entry prompts"
                        )
                        sim_prompts_list = None
        except Exception as e:
            logger.warning(f"SUPERVISOR [multi-sim]: LLM decomposition failed: {e}")

        # Fallback: deterministic prompts per expanded entry.
        if not sim_prompts_list or len(sim_prompts_list) != len(expanded_entries):
            logger.info("SUPERVISOR [multi-sim]: Using deterministic prompt decomposition")
            sim_prompts_list = []
            _styles = ["Prepare", "Process", "Set up", "Generate setup for"]
            for i, e in enumerate(expanded_entries):
                pdb_name = _Path(e["pdb"]).name
                name = e["protein_name"]
                lead = _styles[i % len(_styles)]
                uniprot_hint = ""
                structure_requests = state.get("structure_requests") or {}
                uid_key = _Path(e["pdb"]).stem.lower()
                req = structure_requests.get(uid_key)
                if req and req.get("uniprot_id"):
                    src = req.get("structure_source", "auto")
                    uniprot_hint = (
                        f" Download structure from {src} for UniProt "
                        f"{req['uniprot_id']} if {pdb_name} is not present."
                    )
                sim_prompts_list.append(
                    (
                        f"{lead} simulation for {name} using source structure {pdb_name}. "
                        f"Simulation label is {e['label']} under {e['working_dir']}. "
                        f"Case requirement: {e['case_description']}. {e['case_directive']}"
                        f"{uniprot_hint} "
                        f"Run workflow steps: {agents_desc}."
                    ).strip()
                )
            combined_plan = (
                "Perform combined cross-simulation analysis grouped by protein and component case.\n"
                "1. Compare metrics between case variants (for example protein-only vs ATP-bound).\n"
                "2. Produce cross-protein overlays (RMSD, RMSF, Rg) and summary statistics.\n"
                "3. Generate a consolidated markdown report with case-specific insights."
            )

        sim_prompts = []
        for entry, prompt_text in zip(expanded_entries, sim_prompts_list):
            pdb = entry["pdb"]
            sim_prompts.append(
                {
                    "pdb": str(_Path(pdb).resolve()) if _Path(pdb).exists() else pdb,
                    "label": entry["label"],
                    "prompt": _coerce_plan_text(prompt_text, default=""),
                    "working_dir": entry["working_dir"],
                    "case_id": entry.get("case_id"),
                    "case_description": entry["case_description"],
                    "case_directive": entry.get("case_directive"),
                }
            )

        state["sim_prompts"] = sim_prompts
        state["combined_analysis_plan"] = _coerce_plan_text(combined_plan, default="")

        logger.info(
            f"SUPERVISOR [multi-sim]: Master plan ready - {len(sim_prompts)} simulations, "
            f"labels: {[s['label'] for s in sim_prompts]}"
        )
        log_agent_action(
            agent_name="supervisor",
            action="Generated Multi-Simulation Master Plan",
            details={
                "num_simulations": len(sim_prompts),
                "labels": [s["label"] for s in sim_prompts],
                "component_cases": [c.get("description") for c in component_cases],
                "agents": agents_desc,
                "combined_plan_preview": (combined_plan or "")[:300],
            },
        )
        self._save_multi_sim_master_plan(
            base_working_dir=base_working_dir,
            sim_prompts=sim_prompts,
            combined_plan=combined_plan or "",
            enriched_prompt=enriched_prompt,
            agents_desc=agents_desc,
        )
        return state

    def _save_multi_sim_master_plan(
        self,
        *,
        base_working_dir: str,
        sim_prompts: List[Dict[str, Any]],
        combined_plan: str,
        enriched_prompt: str,
        agents_desc: str,
    ) -> None:
        """Persist overall multi-simulation master plan to {base}/planner/."""
        from datetime import datetime

        plan_data = {
            "title": "Multi-Simulation Master Plan",
            "format": "master_plan",
            "phase": "master",
            "workflow_pipeline": agents_desc,
            "enriched_prompt": enriched_prompt,
            "sim_prompts": sim_prompts,
            "combined_analysis_plan": combined_plan,
            "num_simulations": len(sim_prompts),
            "labels": [s.get("label") for s in sim_prompts],
        }

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md_lines = [
            "# Multi-Simulation Master Plan",
            "",
            f"**Generated:** {ts}",
            f"**Simulations:** {len(sim_prompts)}",
            f"**Pipeline:** {agents_desc}",
            "",
            "## Overall Goal",
            "",
            enriched_prompt or "_N/A_",
            "",
            "## Per-Simulation Prompts",
            "",
        ]
        for idx, sim in enumerate(sim_prompts, 1):
            md_lines += [
                f"### {idx}. {sim.get('label', f'sim_{idx}')}",
                "",
                f"- **PDB:** {sim.get('pdb', 'N/A')}",
                f"- **Directory:** {sim.get('working_dir', 'N/A')}",
                f"- **Case:** {sim.get('case_description', 'N/A')}",
                "",
                _coerce_plan_text(sim.get("prompt"), default="_No prompt text._"),
                "",
            ]
        md_lines += [
            "## Combined Analysis Plan",
            "",
            _coerce_plan_text(combined_plan, default="_No combined analysis plan._"),
        ]

        save_plan_artifacts(
            base_working_dir,
            "planner",
            json_filename="master_plan.json",
            md_filename="master_plan.md",
            history_filename="execution_plans.jsonl",
            plan_data=plan_data,
            md_content="\n".join(md_lines),
            phase="master",
            label="overall",
        )

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
                if state.get("is_multi_simulation") and state.get("multi_sim_phase") == "executing_sims":
                    sim_label = "unknown"
                    sim_idx = state.get("current_sim_index", 0)
                    sim_prompts = state.get("sim_prompts") or []
                    if isinstance(sim_prompts, list) and 0 <= sim_idx < len(sim_prompts):
                        sim_label = sim_prompts[sim_idx].get("label", sim_label)

                    state["errors"].append(
                        f"SimSetup failed after 3 retries for {sim_label} — continuing with next simulation"
                    )
                    state["plan_executed"] = True
                    state["next_node"] = "supervisor"
                    logger.warning(
                        "SimSetup exhausted 3 retries for multi-sim case %s — advancing to next simulation",
                        sim_label,
                    )
                    log_supervisor_routing(
                        state,
                        "supervisor",
                        f"SimSetup failed after 3 retries for {sim_label}; advancing multi-sim loop",
                    )
                    return state

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
