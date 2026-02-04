"""
Clean and simple LLM-Powered MD Workflow Supervisor

Responsibilities:
1. Preprocess and rephrase user prompts
2. Validate input (PDB files, goals)
3. Collaborate with planner to create execution plans
4. Route tasks to field agents based on approved plans
"""

import logging
import yaml
import os
from typing import Any, Dict, Optional, Tuple

from .state import MDState
from .utils import log_supervisor_routing, log_llm_interaction
from .llm import LLMClient
from .planner import MDPlanner

logger = logging.getLogger(__name__)


class MDSupervisor:
    """
    Simple and clean LLM-powered supervisor that:
    - Takes user prompts and rephrases them
    - Validates inputs
    - Collaborates with planner for execution planning
    - Routes to field agents
    """

    def __init__(self, llm_client: Optional[LLMClient] = None, config_path: Optional[str] = None):
        """
        Initialize supervisor with LLM and configuration.

        Args:
            llm_client: LLMClient instance for LLM operations
            config_path: Path to config_supervisor.yaml (auto-detected if None)
        """
        if llm_client is None:
            raise ValueError("llm_client is required for supervisor operation")

        self.llm = llm_client
        self.planner = None  # Lazy-load planner on first use

        # Load configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "config_supervisor.yaml")

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
        1. Input Validation → Preprocess and rephrase user prompt
        2. Create Execution Plan → Collaborate with planner
        3. Assign Field Agent Tasks → Route to appropriate agents
        4. Generate Final Report → Summarize results
        """
        # Lazy-load planner on first use
        if self.planner is None:
            self.planner = MDPlanner(llm_client=self.llm)
        
        logger.info("=" * 60)
        logger.info("SUPERVISOR: Analyzing workflow state and routing decision")
        logger.info("=" * 60)

        # Debug: Check execution plan state
        has_plan = bool(state.get("execution_plan"))
        logger.info(f"SUPERVISOR: execution_plan exists: {has_plan}")
        if has_plan:
            plan = state.get("execution_plan", {})
            logger.info(f"SUPERVISOR: Plan has {len(plan.get('steps', []))} steps")

        # Step 1: Input validation if needed
        if not state.get("raw_pdb") or not state.get("user_goal"):
            state["next_node"] = "input_validation"
            logger.info("SUPERVISOR: Routing to input validation")
            return state

        # Step 2: Create execution plan if not exists
        if not state.get("execution_plan"):
            logger.info("SUPERVISOR: No execution plan found, creating with planner")
            state["next_node"] = "planner"
            return state

        # Step 3: Assign field agent tasks based on plan
        # Check if plan has steps to execute
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
        Validate and preprocess user input.

        Steps:
        1. Rephrase user prompt for clarity
        2. Extract PDB file path
        3. Validate inputs
        4. Set up working directory
        """
        logger.info("INPUT_VALIDATION: Starting input validation")

        user_goal = state.get("user_goal", "")

        # Step 1: Rephrase user prompt using LLM
        if self.llm and self.llm.available:
            rephrased = self._rephrase_user_prompt(user_goal)
            state["rephrased_goal"] = rephrased
            logger.info(f"INPUT_VALIDATION: Rephrased goal: {rephrased[:100]}...")
        else:
            state["rephrased_goal"] = user_goal
            logger.info("INPUT_VALIDATION: LLM unavailable, using original goal")

        # Step 2: Extract and validate PDB path
        pdb_path = self._extract_pdb_path(user_goal)
        if pdb_path:
            state["raw_pdb"] = pdb_path
            logger.info(f"INPUT_VALIDATION: Extracted PDB path: {pdb_path}")

            # Validate file exists
            if not os.path.exists(pdb_path):
                state["warnings"].append(f"PDB file not found: {pdb_path}")
                logger.warning(f"INPUT_VALIDATION: PDB file not found: {pdb_path}")
        else:
            error_msg = "Could not extract PDB file path from user goal"
            state["errors"].append(error_msg)
            logger.error(f"INPUT_VALIDATION: {error_msg}")

        # Step 3: Set working directory
        if pdb_path:
            pdb_dir = os.path.dirname(pdb_path)
            state["working_directory"] = pdb_dir if pdb_dir else "."
            logger.info(f"INPUT_VALIDATION: Working directory set to: {state['working_directory']}")

        # Next step: supervisor routing
        state["next_node"] = "supervisor"
        log_supervisor_routing(
            state, "supervisor", "Input validation complete, supervisor will create plan"
        )

        return state

    def _rephrase_user_prompt(self, user_goal: str) -> str:
        """
        Use LLM to rephrase and clarify user prompt.

        Returns:
            Rephrased goal string
        """
        prompt_template = self.supervisor_config.get("input_validation", {}).get(
            "prompt_rephrase", ""
        )

        prompt = prompt_template.format(user_goal=user_goal)

        try:
            response = self.llm.prompt(prompt)
            
            # Log the LLM interaction
            log_llm_interaction(
                agent_name="supervisor.input_validation",
                prompt=prompt,
                response=response,
                is_mock=not self.llm.available
            )
            
            logger.info("INPUT_VALIDATION: Successfully rephrased user prompt")
            return response
        except Exception as e:
            logger.error(f"INPUT_VALIDATION: Error rephrasing prompt: {e}")
            return user_goal

    def _extract_pdb_path(self, user_goal: str) -> Optional[str]:
        """
        Extract PDB file path from user goal.

        Uses regex patterns defined in config to find PDB file paths.
        """
        import re

        patterns = self.supervisor_config.get("input_validation", {}).get(
            "pdb_search_patterns", []
        )

        for pattern in patterns:
            match = re.search(pattern, user_goal)
            if match:
                pdb_path = match.group(1)
                logger.info(f"INPUT_VALIDATION: Matched PDB path with pattern '{pattern}': {pdb_path}")
                return pdb_path

        logger.warning("INPUT_VALIDATION: No PDB file path found in user goal")
        return None

    def _assign_field_agent_tasks(self, state: MDState) -> MDState:
        """
        Route to appropriate field agents based on approved plan.

        Determines which agent to run next based on:
        1. Execution plan steps
        2. Current workflow progress
        3. Available inputs/outputs
        """
        logger.info("FIELD_AGENT_ASSIGNMENT: Assigning tasks from approved plan")

        plan = state.get("execution_plan", {})
        steps = plan.get("steps", [])

        # Check each step in order
        for step in steps:
            step_name = step.get("name", "").lower()
            agent_name = step.get("agent", "").lower()

            logger.info(f"FIELD_AGENT_ASSIGNMENT: Checking step: {step_name} (agent: {agent_name})")

            # Map agent registry names to workflow node names
            if "preprocessing" in agent_name or "preprocess" in agent_name or "preprocess" in step_name:
                if not state.get("cleaned_pdb"):
                    state["next_node"] = "preprocess"
                    state["preprocessing_plan"] = step
                    logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to preprocessing for step: {step_name}")
                    log_supervisor_routing(state, "preprocess", f"Executing plan step: {step_name}")
                    return state
                else:
                    logger.info(f"FIELD_AGENT_ASSIGNMENT: Preprocessing already complete, skipping")

            elif "setup" in agent_name or "setup" in step_name:
                if not state.get("coordinates"):
                    state["next_node"] = "setup"
                    state["setup_plan"] = step
                    logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to setup for step: {step_name}")
                    log_supervisor_routing(state, "setup", f"Executing plan step: {step_name}")
                    return state
                else:
                    logger.info(f"FIELD_AGENT_ASSIGNMENT: Setup already complete, skipping")

            elif "hpc" in agent_name or "simulation" in agent_name or "hpc" in step_name:
                if not state.get("trajectory"):
                    state["next_node"] = "hpc"
                    state["hpc_plan"] = step
                    logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to HPC for step: {step_name}")
                    log_supervisor_routing(state, "hpc", f"Executing plan step: {step_name}")
                    return state
                else:
                    logger.info(f"FIELD_AGENT_ASSIGNMENT: HPC already complete, skipping")

            elif "analysis" in agent_name or "analysis" in step_name:
                if not state.get("analysis_results"):
                    state["next_node"] = "analysis"
                    state["analysis_plan"] = step
                    logger.info(f"FIELD_AGENT_ASSIGNMENT: Routing to analysis for step: {step_name}")
                    log_supervisor_routing(state, "analysis", f"Executing plan step: {step_name}")
                    return state
                else:
                    logger.info(f"FIELD_AGENT_ASSIGNMENT: Analysis already complete, skipping")

        # All field agents complete - mark plan as executed
        logger.info("FIELD_AGENT_ASSIGNMENT: All plan steps completed")
        state["plan_executed"] = True
        state["next_node"] = "final_report"
        log_supervisor_routing(state, "final_report", "All workflow tasks complete")
        return state

    # ===== HELPER METHODS =====

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
        progress = (len(completed) / (total + 2)) * 100  # +2 for validation and planning
        return f"Progress: {completed} ({progress:.0f}%)"
