"""
Clean and Simple LLM-Powered MD Workflow Supervisor

Responsibilities:
1. Analyze PDB structure and validate components
2. Enrich user prompt ONCE with all context (Single LLM call for entire workflow)  
3. Validate input feasibility (PDB files, parameters, user intent)
4. Collaborate with planner to create execution plans
5. Route tasks to field agents in STRICT ORDER: preprocessing → simsetup → hpc → analysis → reporter
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

        Pipeline:
        1. Detect Subtask Type → If analysis-only, setup-only, etc., route accordingly
        2. Input Validation → PDB analysis and feasibility check (skipped for analysis-only)
        3. Unified Enrichment → SINGLE LLM call to enrich prompt with all context
        4. Create Execution Plan → Collaborate with planner using enriched prompt
        5. Execute Agents → Route to field agents in STRICT ORDER (preprocess → simsetup → hpc → analysis → reporter)
        6. Generate Final Report → Summarize results
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
                if subtask_type == "multi_agent":
                    logger.info(f"SUPERVISOR: Agent list: {state.get('agent_list', [])}")
            
            # Store required inputs for this subtask
            required_inputs = detect_task_required_inputs(subtask_type, state.get("agent_list"))
            state["required_inputs"] = required_inputs
            state["subtask_type_initialized"] = True

        # Check if we're returning from a field agent - increment agent counter
        current_node = state.get("current_node", "")
        if current_node in ["preprocess", "setup", "hpc", "analysis", "reporter"]:
            current_agent_idx = state.get("current_agent_idx", 0)
            logger.info(f"SUPERVISOR: Returned from {current_node}, advancing from agent {current_agent_idx} to {current_agent_idx + 1}")
            state["current_agent_idx"] = current_agent_idx + 1

        # Debug: Check workflow state
        has_plan = bool(state.get("execution_plan"))
        logger.info(f"SUPERVISOR: execution_plan exists: {has_plan}")
        if has_plan:
            current_agent_idx = state.get("current_agent_idx", 0)
            subtask_type = state.get("subtask_type", "full_task")
            from src.supervisor.unified_enricher import get_agent_execution_order
            required_agents = get_agent_execution_order(subtask_type, state)
            total_agents = len(required_agents)
            logger.info(f"SUPERVISOR: Agent progress: {current_agent_idx}/{total_agents} ({required_agents})")

        # Step 1: Input validation if needed (unified for all task types)
        required_inputs = state.get("required_inputs", {})
        subtask_type = state.get("subtask_type", "full_task")
        
        # Check if we need to validate inputs.
        # IMPORTANT: check task-specific "already validated" flags FIRST to
        # avoid looping back into input_validation after it completes.
        needs_validation = False
        if subtask_type == "reporter_only":
            # Reporter only needs its own flag; never requires pdb_analysis
            if not state.get("reporter_validated"):
                needs_validation = True
        elif subtask_type == "analysis_only":
            if not state.get("analysis_validated"):
                needs_validation = True
        elif subtask_type == "multi_agent":
            if not state.get("multi_agent_validated"):
                needs_validation = True
        else:
            # Full / PDB-requiring tasks
            if not state.get("pdb_analysis") and required_inputs.get("pdb_analysis_required", True):
                needs_validation = True
        
        if needs_validation and state.get("user_goal"):
            logger.info(f"SUPERVISOR: Routing to unified input validation for task type: {subtask_type}")
            state["next_node"] = "input_validation"
            return state
        
        # Check for missing required inputs (PDB-based tasks only)
        if subtask_type not in ("reporter_only", "analysis_only", "multi_agent"):
            if not state.get("raw_pdb") and required_inputs.get("pdb_required", True):
                state["next_node"] = "input_validation"
                logger.info("SUPERVISOR: Routing to input validation - missing raw_pdb for this task")
                return state

        # Step 2: Unified prompt enrichment (SINGLE enrichment for entire workflow)
        # This runs ONCE after input validation and before planning
        validated = (state.get("pdb_analysis") or 
                    state.get("analysis_validated") or 
                    state.get("reporter_validated") or
                    state.get("multi_agent_validated"))
        
        if validated and not state.get("enriched_prompt"):
            logger.info("SUPERVISOR: Input validated, enriching prompt with unified enrichment")
            enriched = enrich_prompt_unified(state, self.llm, self.supervisor_config)
            state["enriched_prompt"] = enriched
            state["rephrased_goal"] = enriched  # Keep for backward compatibility
            logger.info(f"SUPERVISOR: Unified enrichment complete ({len(enriched)} chars)")
        
        # Step 3: Create execution plan if not exists
        # Route to planner for all validated tasks (including reporter_only, analysis_only, multi_agent)
        if not state.get("execution_plan") and state.get("enriched_prompt"):
            logger.info("SUPERVISOR: Enriched prompt ready, creating execution plan with planner")
            state["next_node"] = "planner"
            return state
        
        # Step 3.5: Extract agent-specific plans after planner returns
        # This ensures each agent receives only its relevant instructions
        if state.get("execution_plan") and not state.get("preprocessing_instructions"):
            logger.info("SUPERVISOR: Extracting agent-specific plans from full execution plan")
            state = self._extract_agent_specific_plans(state)

        # Step 4: Assign field agent tasks using STRICT ORDERING
        plan = state.get("execution_plan", {})
        if plan and not state.get("plan_executed"):
            logger.info("SUPERVISOR: Execution plan ready, assigning field agent tasks with strict ordering")
            return self._assign_field_agent_tasks(state)

        # Step 5: Handle errors and complete
        if state.get("errors"):
            logger.error(
                f"SUPERVISOR: Workflow has {len(state['errors'])} errors. "
                f"Routing to final report."
            )
            state["next_node"] = "final_report"
            return state

        # Step 6: All tasks complete
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
                state["errors"].append("SimSetup failed after 3 retries")
                state["current_agent_idx"] = current_agent_idx + 1
                return self._assign_field_agent_tasks(state)
            
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
            
            user_excluded_hpc = any(phrase in combined_goals for phrase in [
                "no hpc", "skip hpc", "do not submit", "don't submit", "setup only", 
                "without hpc", "no simulation", "local only"
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
