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
import re
from typing import Any, Dict, Optional

from ..state import MDState
from ..utils import log_supervisor_routing, log_agent_action
from ..llm import LLMClient
from ..planner import MDPlanner
from .tools import (
    parse_component_selection,
    validate_feasibility,
    enrich_user_prompt,
    enrich_analysis_prompt,
    detect_task_required_inputs
)

# Import PDB analyzer
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
        Main supervisor routing logic with support for subtask-specific workflows.

        Pipeline:
        1. Detect Subtask Type → If analysis-only, setup-only, etc., route accordingly
        2. Input Validation → PDB analysis and feasibility check (skipped for analysis-only)
        3. Create Execution Plan → Collaborate with planner
        4. Execute Steps One-by-One → Route to field agents iteratively
        5. Generate Final Report → Summarize results
        """
        # Lazy-load planner on first use
        if self.planner is None:
            self.planner = MDPlanner(llm_client=self.llm)
        
        logger.info("=" * 60)
        logger.info("SUPERVISOR: Analyzing workflow state and routing decision")
        logger.info("=" * 60)

        # Get subtask type from state (passed from config via command-line args)
        if not state.get("subtask_type_initialized"):
            subtask_type = state.get("subtask_type")
            if subtask_type:
                logger.info(f"SUPERVISOR: Subtask type: {subtask_type}")
            
            # Store required inputs for this subtask
            required_inputs = detect_task_required_inputs(subtask_type)
            state["required_inputs"] = required_inputs
            state["subtask_type_initialized"] = True

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

        # Step 1: Input validation if needed (unified for all task types)
        required_inputs = state.get("required_inputs", {})
        subtask_type = state.get("subtask_type", "full_task")
        
        # Check if we need to validate inputs (any task type)
        needs_validation = False
        if not state.get("pdb_analysis") and required_inputs.get("pdb_analysis_required", True):
            needs_validation = True
        elif subtask_type == "analysis_only" and not state.get("analysis_validated"):
            needs_validation = True
        
        if needs_validation and state.get("user_goal"):
            logger.info(f"SUPERVISOR: Routing to unified input validation for task type: {subtask_type}")
            state["next_node"] = "input_validation"
            return state
        
        # Check for missing required inputs
        if not state.get("raw_pdb") and required_inputs.get("pdb_required", True):
            state["next_node"] = "input_validation"
            logger.info("SUPERVISOR: Routing to input validation - missing raw_pdb for this task")
            return state

        # Step 2: Create execution plan if not exists
        if not state.get("execution_plan") and (state.get("pdb_analysis") or state.get("analysis_validated")):
            logger.info("SUPERVISOR: Validation complete, creating execution plan with planner")
            state["next_node"] = "planner"
            return state
        
        # Step 2.5: Extract agent-specific plans after planner returns
        # This ensures each agent receives only its relevant instructions
        if state.get("execution_plan") and not state.get("preprocessing_instructions"):
            logger.info("SUPERVISOR: Extracting agent-specific plans from full execution plan")
            state = self._extract_agent_specific_plans(state)

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
        Universal input validation node for all task types.
        
        Uses the unified validate_and_enrich_inputs() function from tools.py
        to handle both PDB-based tasks and analysis-only tasks.
        """
        from .tools import validate_and_enrich_inputs
        
        logger.info("=" * 60)
        logger.info("INPUT_VALIDATION: Starting unified input validation")
        logger.info("=" * 60)
        
        subtask_type = state.get("subtask_type", "full_task")
        
        log_agent_action(
            agent_name="supervisor.input_validation",
            action=f"Starting Unified Input Validation ({subtask_type})",
            details={
                "user_goal": state.get("user_goal", "")[:200],
                "task_type": subtask_type
            }
        )
        
        # Call unified validation function
        state = validate_and_enrich_inputs(
            state=state,
            subtask_type=subtask_type,
            llm_client=self.llm,
            config=self.supervisor_config,
            analyze_pdb_tool=analyze_pdb,
            logger=logger
        )
        
        # Set validation flags based on task type
        if subtask_type == "analysis_only":
            state["analysis_validated"] = True
        else:
            # PDB-based tasks are validated
            pass
        
        log_supervisor_routing(
            state, "supervisor",
            f"Input validation complete for {subtask_type}, returning to supervisor for planning"
        )
        
        return state

    def _extract_agent_specific_plans(self, state: MDState) -> MDState:
        """
        Extract agent-specific instructions from the full execution plan.
        
        This centralizes the extraction logic that was duplicated across all agents.
        After planner creates the full plan, this method parses it and stores
        agent-specific sections in state for direct access by each agent.
        
        Args:
            state: Current workflow state with execution_plan containing full_plan
            
        Returns:
            Updated state with agent-specific instruction keys:
            - preprocessing_instructions
            - setup_instructions
            - hpc_instructions
            - analysis_instructions
        """
        import re
        
        execution_plan = state.get("execution_plan", {})
        full_plan = execution_plan.get("full_plan", "")
        
        if not full_plan:
            logger.warning("No full_plan found in execution_plan, skipping agent-specific extraction")
            return state
        
        logger.info(f"Extracting agent-specific instructions from {len(full_plan)} char plan")
        
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
                # Try multiple heading patterns
                patterns = [
                    # Markdown ### heading
                    rf'###\s*{re.escape(agent_name)}.*?\n(.*?)(?=###|\Z)',
                    # Markdown ## heading  
                    rf'##\s*{re.escape(agent_name)}.*?\n(.*?)(?=##|\Z)',
                    # Bold heading
                    rf'\*\*{re.escape(agent_name)}\*\*.*?\n(.*?)(?=\*\*[A-Z]|\Z)',
                    # Section number patterns
                    rf'\d+\..*?{re.escape(agent_name)}.*?\n(.*?)(?=\d+\.|\Z)',
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE)
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

    def _validate_analysis_inputs(self, state: MDState) -> MDState:
        """
        DEPRECATED: Use input_validation_node() instead.
        
        This method is preserved for backward compatibility but now redirects
        to the unified validate_and_enrich_inputs() function via input_validation_node().
        """
        logger.warning("_validate_analysis_inputs is deprecated. Use input_validation_node() instead.")
        return self.input_validation_node(state)

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
            # Check for repeated failures to prevent infinite loops
            preprocess_retry_count = state.get("preprocess_retry_count", 0)
            max_retries = 3
            
            if preprocess_retry_count >= max_retries:
                error_msg = f"Preprocessing agent failed {preprocess_retry_count} times, skipping to avoid infinite loop"
                logger.error(f"FIELD_AGENT_ASSIGNMENT: {error_msg}")
                state["errors"].append(error_msg)
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)
            
            if not state.get("cleaned_pdb"):
                # Track retry attempts for this specific step
                if state.get("last_preprocess_step") == step_number:
                    state["preprocess_retry_count"] = preprocess_retry_count + 1
                    logger.warning(f"FIELD_AGENT_ASSIGNMENT: Preprocessing retry #{state['preprocess_retry_count']} for step {step_number}")
                else:
                    state["preprocess_retry_count"] = 0
                    state["last_preprocess_step"] = step_number
                
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
            # Check for repeated failures to prevent infinite loops
            setup_retry_count = state.get("setup_retry_count", 0)
            max_retries = 3
            
            if setup_retry_count >= max_retries:
                error_msg = f"Setup agent failed {setup_retry_count} times, skipping to avoid infinite loop"
                logger.error(f"FIELD_AGENT_ASSIGNMENT: {error_msg}")
                state["errors"].append(error_msg)
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)
            
            if not state.get("coordinates"):
                # Track retry attempts for this specific step
                if state.get("last_setup_step") == step_number:
                    state["setup_retry_count"] = setup_retry_count + 1
                    logger.warning(f"FIELD_AGENT_ASSIGNMENT: Setup retry #{state['setup_retry_count']} for step {step_number}")
                else:
                    state["setup_retry_count"] = 0
                    state["last_setup_step"] = step_number
                
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
            # Check if user explicitly excluded HPC
            user_goal = state.get("user_goal", "").lower()
            rephrased_goal = state.get("rephrased_goal", "").lower()
            combined_goals = f"{user_goal} {rephrased_goal}"
            
            user_excluded_hpc = any(phrase in combined_goals for phrase in [
                "no hpc", "skip hpc", "do not submit", "don't submit", "do not use hpc",
                "no job submission", "no simulation", "setup only", "without hpc",
                "do not do hpc", "don't do hpc", "not do hpc", "no hpc job",
                "skip job submission", "skip simulation", "local only", "locally only"
            ])
            
            if user_excluded_hpc:
                logger.info(f"FIELD_AGENT_ASSIGNMENT: User explicitly excluded HPC - skipping step {step_number}")
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Detection in: '{combined_goals[:200]}'")
                state["warnings"].append(f"Skipping HPC step as per user request: {step_name}")
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)
            
            # Check for failures - NO RETRIES, fail once and move on
            hpc_retry_count = state.get("hpc_retry_count", 0)
            
            if hpc_retry_count >= 1:
                error_msg = f"HPC agent failed, stopping (no retries)"
                logger.error(f"FIELD_AGENT_ASSIGNMENT: {error_msg}")
                state["errors"].append(error_msg)
                state["warnings"].append("HPC execution skipped due to failure - simulation not submitted")
                # Mark step as attempted and move on
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)
            
            if not state.get("job_id"):
                # Check if we've already tried this step (no retries allowed)
                if state.get("last_hpc_step") == step_number:
                    state["hpc_retry_count"] = hpc_retry_count + 1
                    logger.error(f"FIELD_AGENT_ASSIGNMENT: HPC already attempted for step {step_number}, no retry allowed")
                    state["errors"].append("HPC agent already attempted, stopping to avoid retries")
                    state["current_step"] = current_step_idx + 1
                    return self._assign_field_agent_tasks(state)
                else:
                    state["hpc_retry_count"] = 0
                    state["last_hpc_step"] = step_number
                
                state["next_node"] = "hpc"
                state["hpc_plan"] = current_step
                logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to HPC for step {step_number} (first attempt only)")
                log_supervisor_routing(state, "hpc", f"Executing Step {step_number}: {step_name}")
                return state
            else:
                logger.info(f"FIELD_AGENT_ASSIGNMENT: HPC already complete, advancing to next step")
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)

        elif "analysis" in agent_name:
            # Check for repeated failures to prevent infinite loops
            analysis_retry_count = state.get("analysis_retry_count", 0)
            max_retries = 3
            
            if analysis_retry_count >= max_retries:
                error_msg = f"Analysis agent failed {analysis_retry_count} times, skipping to avoid infinite loop"
                logger.error(f"FIELD_AGENT_ASSIGNMENT: {error_msg}")
                state["errors"].append(error_msg)
                state["current_step"] = current_step_idx + 1
                return self._assign_field_agent_tasks(state)
            
            if not state.get("analysis_results"):
                # Track retry attempts for this specific step
                if state.get("last_analysis_step") == step_number:
                    state["analysis_retry_count"] = analysis_retry_count + 1
                    logger.warning(f"FIELD_AGENT_ASSIGNMENT: Analysis retry #{state['analysis_retry_count']} for step {step_number}")
                else:
                    state["analysis_retry_count"] = 0
                    state["last_analysis_step"] = step_number
                
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
