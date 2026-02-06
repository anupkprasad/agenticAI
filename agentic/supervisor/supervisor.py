"""
Clean and Simple LLM-Powered MD Workflow Supervisor

Responsibilities:
1. Analyze PDB structure and validate components
2. Preprocess and rephrase user prompts into structured form
3. Validate input feasibility (PDB files, parameters, user intent)
4. Collaborate with planner to create execution plans
5. Route tasks to field agents based on approved plans
"""

import logging
import yaml
import os
from typing import Any, Dict, Optional

from ..state import MDState
from ..utils import log_supervisor_routing, log_agent_action
from ..llm import LLMClient
from ..planner import MDPlanner
from .tools import (
    extract_pdb_path,
    parse_component_selection,
    validate_feasibility,
    enrich_user_prompt
)

# Import PDB analyzer
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../..'))
from src.utils.pdb_analyzer import analyze_pdb

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

    def supervisor_node(self, state: MDState) -> MDState:
        """
        Main supervisor routing logic.

        Pipeline:
        1. Input Validation → PDB analysis and feasibility check
        2. Create Execution Plan → Collaborate with planner
        3. Execute Steps One-by-One → Route to field agents iteratively
        4. Generate Final Report → Summarize results
        """
        # Lazy-load planner on first use
        if self.planner is None:
            self.planner = MDPlanner(llm_client=self.llm)
        
        logger.info("=" * 60)
        logger.info("SUPERVISOR: Analyzing workflow state and routing decision")
        logger.info("=" * 60)

        # Check if we're returning from a field agent - increment step counter
        current_node = state.get("current_node", "")
        if current_node in ["preprocess", "setup", "hpc", "analysis"]:
            current_step = state.get("current_step", 0)
            logger.info(f"SUPERVISOR: Returned from {current_node}, advancing from step {current_step} to {current_step + 1}")
            state["current_step"] = current_step + 1

        # Debug: Check execution plan state
        has_plan = bool(state.get("execution_plan"))
        logger.info(f"SUPERVISOR: execution_plan exists: {has_plan}")
        if has_plan:
            plan = state.get("execution_plan", {})
            current_step_num = state.get("current_step", 0)
            total_steps = len(plan.get('steps', []))
            logger.info(f"SUPERVISOR: Plan progress: Step {current_step_num}/{total_steps}")

        # Step 1: Input validation if needed
        if not state.get("pdb_analysis") and state.get("user_goal"):
            state["next_node"] = "input_validation"
            logger.info("SUPERVISOR: Routing to input validation for PDB analysis and feasibility check")
            return state
        
        # Check for missing required inputs
        if not state.get("raw_pdb") or not state.get("user_goal"):
            state["next_node"] = "input_validation"
            logger.info("SUPERVISOR: Routing to input validation - missing raw_pdb or user_goal")
            return state

        # Step 2: Create execution plan if not exists
        if not state.get("execution_plan") and state.get("pdb_analysis"):
            logger.info("SUPERVISOR: Validation complete, creating execution plan with planner")
            state["next_node"] = "planner"
            return state

        # Step 3: Assign field agent tasks based on plan
        plan = state.get("execution_plan", {})
        if plan.get("steps") and not state.get("plan_executed"):
            logger.info("SUPERVISOR: Execution plan ready, assigning field agent tasks")
            return self._assign_field_agent_tasks(state)

        # Step 4: Handle errors and complete
        if state.get("errors"):
            logger.error(
                f"SUPERVISOR: Workflow has {len(state['errors'])} errors. "
                f"Routing to final report."
            )
            state["next_node"] = "final_report"
            return state

        # Step 5: All tasks complete
        logger.info("SUPERVISOR: All workflow tasks completed")
        state["next_node"] = "final_report"
        return state

    def input_validation_node(self, state: MDState) -> MDState:
        """
        Validate and preprocess user input with PDB analysis.

        Steps:
        1. Extract PDB file path
        2. Analyze PDB structure (components, composition)
        3. Parse user intent and component selection
        4. Validate feasibility of parameters
        5. Create structured prompt for planner
        """
        logger.info("=" * 60)
        logger.info("INPUT_VALIDATION: Starting comprehensive input validation with PDB analysis")
        logger.info("=" * 60)
        
        log_agent_action(
            agent_name="supervisor.input_validation",
            action="Starting Input Validation & PDB Analysis",
            details={
                "user_goal": state.get("user_goal", "")[:200]
            }
        )

        user_goal = state.get("user_goal", "")

        # Step 1: Extract and validate PDB path
        search_patterns = self.supervisor_config.get("input_validation", {}).get(
            "pdb_search_patterns", []
        )
        pdb_path = extract_pdb_path(user_goal, search_patterns)
        
        if pdb_path:
            state["raw_pdb"] = pdb_path
            logger.info(f"INPUT_VALIDATION: Extracted PDB path: {pdb_path}")

            # Validate file exists
            if not os.path.exists(pdb_path):
                state["errors"].append(f"PDB file not found: {pdb_path}")
                logger.error(f"INPUT_VALIDATION: PDB file not found: {pdb_path}")
                state["next_node"] = "supervisor"
                return state
        else:
            error_msg = "Could not extract PDB file path from user goal"
            state["errors"].append(error_msg)
            logger.error(f"INPUT_VALIDATION: {error_msg}")
            state["next_node"] = "supervisor"
            return state

        # Step 2: Analyze PDB structure
        logger.info(f"INPUT_VALIDATION: Analyzing PDB structure: {pdb_path}")
        
        pdb_analysis_result = analyze_pdb.invoke({"pdb_file": pdb_path})
        
        if not pdb_analysis_result.get("success"):
            error_msg = f"PDB analysis failed: {pdb_analysis_result.get('error', 'Unknown error')}"
            state["warnings"].append(error_msg)
            logger.warning(f"INPUT_VALIDATION: {error_msg}")
            logger.warning("INPUT_VALIDATION: Continuing with limited analysis, will use defaults")
            
            # Create minimal analysis for fallback
            state["pdb_analysis"] = {
                "total_atoms": 0,
                "total_residues": 0,
                "protein": {"present": True},
                "ligands": {"present": False},
                "water": {"present": False},
                "components_available": {},
                "chain_ids": []
            }
        else:
            # Store analysis in state
            state["pdb_analysis"] = pdb_analysis_result.get("analysis", {})
            logger.info(f"INPUT_VALIDATION: PDB analysis complete - {pdb_analysis_result.get('message', '')}")
            
            # Log detailed analysis
            analysis = state["pdb_analysis"]
            
            # Extract protein sequences if available
            protein_sequences = {}
            if analysis.get("protein", {}).get("present"):
                chains_info = analysis.get("protein", {}).get("chains", {})
                for chain_id, chain_data in chains_info.items():
                    sequence = chain_data.get("sequence", "")
                    if sequence:
                        protein_sequences[chain_id] = sequence
            
            # Build details dict
            details = {
                "file": pdb_path,
                "total_atoms": analysis.get("total_atoms", 0),
                "total_residues": analysis.get("total_residues", 0),
                "components_available": analysis.get("components_available", {})
            }
            
            # Add protein sequences if present
            if protein_sequences:
                details["protein_sequences"] = protein_sequences
            
            log_agent_action(
                agent_name="supervisor.input_validation",
                action="PDB Structure Analysis",
                details=details
            )
        
        # Get analysis for subsequent steps
        analysis = state["pdb_analysis"]

        # Step 3: Parse user intent and determine component selection
        component_selection = parse_component_selection(user_goal, analysis)
        state["component_selection"] = component_selection
        logger.info(f"INPUT_VALIDATION: Component selection: {component_selection}")

        # Step 4: Validate feasibility
        validation_result = validate_feasibility(user_goal, analysis, component_selection)
        
        if not validation_result["is_feasible"]:
            for error in validation_result["errors"]:
                state["errors"].append(error)
                logger.error(f"INPUT_VALIDATION: Feasibility error - {error}")
            state["next_node"] = "supervisor"
            return state
        
        for warning in validation_result["warnings"]:
            state["warnings"].append(warning)
            logger.warning(f"INPUT_VALIDATION: {warning}")

        # Step 5: Enrich user prompt with validated information for planner
        enriched_prompt = enrich_user_prompt(
            user_goal, analysis, self.llm, self.supervisor_config
        )
        state["structured_prompt"] = enriched_prompt
        state["rephrased_goal"] = enriched_prompt
        
        logger.info(f"INPUT_VALIDATION: Enriched prompt created: {enriched_prompt[:150]}...")
        
        log_agent_action(
            agent_name="supervisor.input_validation",
            action="Input Validation Complete",
            details={
                "original_goal": user_goal[:100],
                "enriched_prompt": enriched_prompt[:300],
                "pdb_file": pdb_path
            }
        )

        # Step 6: Set working directory
        if pdb_path:
            pdb_dir = os.path.dirname(pdb_path)
            state["working_directory"] = pdb_dir if pdb_dir else "."
            logger.info(f"INPUT_VALIDATION: Working directory set to: {state['working_directory']}")

        # Log final validation summary
        logger.info("=" * 60)
        logger.info("INPUT_VALIDATION: Validation complete - ready for planning")
        logger.info(f"  - PDB Analysis: {'✓ Success' if not state.get('warnings') else '⚠ With warnings'}")
        logger.info(f"  - Component Selection: {component_selection}")
        logger.info(f"  - Enriched Prompt: {enriched_prompt[:80]}...")
        logger.info("=" * 60)

        # Next step: supervisor routing
        state["next_node"] = "supervisor"
        log_supervisor_routing(
            state, "supervisor", "Input validation complete with PDB analysis, returning to supervisor for planning"
        )

        return state

    def _assign_field_agent_tasks(self, state: MDState) -> MDState:
        """
        Route to appropriate field agents based on approved plan.
        
        Executes plan steps one-by-one in order, respecting dependencies.
        """
        logger.info("FIELD_AGENT_ASSIGNMENT: Assigning tasks from approved plan")

        plan = state.get("execution_plan", {})
        steps = plan.get("steps", [])
        current_step_idx = state.get("current_step", 0)
        
        if current_step_idx >= len(steps):
            # All steps complete
            logger.info("FIELD_AGENT_ASSIGNMENT: All plan steps completed")
            state["plan_executed"] = True
            state["next_node"] = "final_report"
            log_supervisor_routing(state, "final_report", "All workflow tasks complete")
            return state
        
        # Get current step to execute
        current_step = steps[current_step_idx]
        step_name = current_step.get("name", "Unnamed")
        step_number = current_step.get("step_number", current_step_idx + 1)
        agent_name = current_step.get("agent", "").lower()
        
        logger.info(f"FIELD_AGENT_ASSIGNMENT: Executing Step {step_number}: {step_name} (agent: {agent_name})")
        
        # Check dependencies
        dependencies = current_step.get("dependencies", [])
        for dep_step_num in dependencies:
            dep_step_idx = dep_step_num - 1
            if dep_step_idx >= current_step_idx:
                error_msg = f"Step {step_number} dependency error: Step {dep_step_num} not yet executed"
                logger.error(f"FIELD_AGENT_ASSIGNMENT: {error_msg}")
                state["errors"].append(error_msg)
                state["next_node"] = "final_report"
                return state
        
        # Route to appropriate agent based on agent name
        if "preprocessing" in agent_name or "preprocess" in agent_name:
            if not state.get("cleaned_pdb"):
                state["next_node"] = "preprocess"
                state["preprocessing_plan"] = current_step
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to preprocessing for step {step_number}")
                log_supervisor_routing(state, "preprocess", f"Executing Step {step_number}: {step_name}")
                return state
            else:
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Preprocessing already complete, advancing to next step")
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)

        elif "setup" in agent_name or "simsetup" in agent_name:
            if not state.get("coordinates"):
                state["next_node"] = "setup"
                state["setup_plan"] = current_step
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to setup for step {step_number}")
                log_supervisor_routing(state, "setup", f"Executing Step {step_number}: {step_name}")
                return state
            else:
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Setup already complete, advancing to next step")
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)

        elif "hpc" in agent_name or "simulation" in agent_name:
            if not state.get("job_id"):
                state["next_node"] = "hpc"
                state["hpc_plan"] = current_step
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to HPC for step {step_number}")
                log_supervisor_routing(state, "hpc", f"Executing Step {step_number}: {step_name}")
                return state
            else:
                logger.info(f"FIELD_AGENT_ASSIGNMENT: HPC already complete, advancing to next step")
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)

        elif "analysis" in agent_name:
            if not state.get("analysis_results"):
                state["next_node"] = "analysis"
                state["analysis_plan"] = current_step
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to analysis for step {step_number}")
                log_supervisor_routing(state, "analysis", f"Executing Step {step_number}: {step_name}")
                return state
            else:
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Analysis already complete, advancing to next step")
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)
        
        else:
            # Unknown agent
            error_msg = f"Unknown agent '{agent_name}' for step {step_number}"
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

        total = len(self.workflow_config.get("default_pipeline", []))
        progress = (len(completed) / (total + 2)) * 100
        return f"Progress: {completed} ({progress:.0f}%)"
