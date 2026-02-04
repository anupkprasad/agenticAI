"""
MD Workflow Planner Agent - Simplified Template-Based

Creates execution plans using templates from config.yaml.
No complex LLM parsing - simple keyword matching and template expansion.
"""
import logging
import yaml
import os
from typing import Dict, Any, Optional, List
from ..state import MDState
from ..llm import LLMClient
from ..utils import log_supervisor_routing, log_llm_interaction
from ..programmer import MDProgrammer

logger = logging.getLogger(__name__)


class MDPlanner:
    """
    Simplified template-based planner.
    Uses keyword matching against config templates to create execution plans.
    """
    
    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        
        self.llm = llm_client
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "config.yaml"
        )
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize programmer as internal component
        self.programmer = MDProgrammer(llm_client=self.llm)
        
        logger.info("MD Planner initialized (template-based)")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load planner configuration from YAML."""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                config = yaml.safe_load(f) or {}
                logger.info(f"Loaded planner config from {self.config_path}")
                return config
        else:
            logger.warning(f"Config not found: {self.config_path}, using defaults")
            return {"planner": {"templates": {}}}
    
    def planner_node(self, state: MDState) -> MDState:
        """Main planner node - creates execution plan."""
        
        logger.info("=" * 60)
        logger.info("PLANNER: Creating execution plan")
        logger.info("=" * 60)
        
        user_goal = state.get("rephrased_goal") or state.get("user_goal", "")
        validated_pdb = state.get("raw_pdb", "")
        
        # Create plan from templates
        plan = self._create_plan_from_templates(user_goal, validated_pdb, state)
        
        # Store in state
        state["execution_plan"] = plan
        state["next_node"] = "supervisor"
        
        num_steps = len(plan.get("steps", []))
        logger.info(f"PLANNER: Created plan with {num_steps} steps")
        
        # Log detailed plan to conversation log
        from ..utils import log_agent_action
        plan_details = {
            "title": plan.get("title", "N/A"),
            "summary": plan.get("summary", "N/A"),
            "total_steps": num_steps,
            "steps": []
        }
        
        for step in plan.get("steps", []):
            plan_details["steps"].append({
                "number": step.get("number", "?"),
                "name": step.get("name", "Unnamed"),
                "agent": step.get("agent", "unknown"),
                "description": step.get("description", "")[:100]
            })
        
        log_agent_action(
            agent_name="planner",
            action="Generated Execution Plan",
            details=plan_details
        )
        
        # Log routing
        log_supervisor_routing(
            state, 
            "supervisor",
            f"Planner: Created plan with {num_steps} steps. Returning to supervisor."
        )
        
        return state
    
    def _create_plan_from_templates(
        self, 
        user_goal: str, 
        validated_pdb: str,
        state: MDState
    ) -> Dict[str, Any]:
        """Create plan using keyword-based templates."""
        
        goal_lower = user_goal.lower()
        templates = self.config.get("planner", {}).get("templates", {})
        
        # Collect matching steps
        plan_steps = []
        
        for template_name, template in templates.items():
            keywords = template.get("keywords", [])
            
            # Check if any keyword matches
            if any(kw in goal_lower for kw in keywords):
                logger.info(f"PLANNER: Matched template '{template_name}'")
                
                for step_template in template.get("default_steps", []):
                    step = {
                        "number": f"Step {len(plan_steps) + 1}",
                        "name": step_template.get("name", "Unnamed Step"),
                        "agent": step_template.get("agent", "unknown"),
                        "description": step_template.get("description", ""),
                        "tools": step_template.get("tools", []),
                        "dependencies": [f"Step {len(plan_steps)}"] if plan_steps else [],
                        "type": "automated"
                    }
                    plan_steps.append(step)
                    logger.info(f"  - Added step: {step['name']} (agent: {step['agent']})")
        
        # Build plan
        plan = {
            "title": f"Execution Plan: {user_goal[:40]}",
            "summary": f"Template-based plan with {len(plan_steps)} step(s)",
            "steps": plan_steps,
            "method": "template_based",
            "pdb_file": validated_pdb
        }
        
        logger.info(f"PLANNER: Plan complete with {len(plan_steps)} steps")
        return plan
