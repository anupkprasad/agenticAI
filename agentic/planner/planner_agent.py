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
        """Main planner node - creates execution plan from structured prompt."""
        
        logger.info("=" * 60)
        logger.info("PLANNER: Creating execution plan from structured prompt")
        logger.info("=" * 60)
        
        # Use structured prompt if available, otherwise fall back to rephrased/original goal
        structured_prompt = state.get("structured_prompt") or state.get("rephrased_goal") or state.get("user_goal", "")
        pdb_path = state.get("raw_pdb", "")
        pdb_analysis = state.get("pdb_analysis", {})
        component_selection = state.get("component_selection", {})
        
        logger.info(f"PLANNER: Using structured prompt: {structured_prompt[:100]}...")
        
        # Create plan from structured prompt and PDB analysis
        plan = self._create_plan_from_analysis(
            structured_prompt, 
            pdb_path, 
            pdb_analysis,
            component_selection,
            state
        )
        
        # Store in state
        state["execution_plan"] = plan
        state["current_step"] = 0  # Initialize step counter
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
                "number": step.get("step_number", "?"),
                "name": step.get("name", "Unnamed"),
                "agent": step.get("agent", "unknown"),
                "description": step.get("description", "")[:100],
                "inputs": step.get("inputs", {}),
                "expected_outputs": step.get("expected_outputs", [])
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
    
    def _create_plan_from_analysis(
        self,
        structured_prompt: str,
        pdb_path: str,
        pdb_analysis: Dict[str, Any],
        component_selection: Dict[str, Any],
        state: MDState
    ) -> Dict[str, Any]:
        """
        Create detailed execution plan based on PDB analysis and component selection.
        
        This creates dependency-aware plans with clear inputs/outputs for each step.
        """
        logger.info("PLANNER: Creating plan from PDB analysis")
        
        plan_steps = []
        step_number = 1
        
        # Determine what preprocessing is needed
        summary = pdb_analysis.get("summary", {})
        
        # Step 1: Preprocessing (if needed)
        preprocessing_tasks = []
        if summary.get("needs_hydrogen_addition"):
            preprocessing_tasks.append("add missing hydrogens")
        if pdb_analysis.get("water", {}).get("present"):
            preprocessing_tasks.append("remove water molecules")
        if component_selection.get("ligand") is False and pdb_analysis.get("ligands", {}).get("present"):
            preprocessing_tasks.append("remove ligand")
        if component_selection.get("specific_chains"):
            preprocessing_tasks.append(f"extract chains {component_selection['specific_chains']}")
        
        if preprocessing_tasks or not state.get("cleaned_pdb"):
            preprocess_step = {
                "step_number": step_number,
                "name": "Preprocess PDB Structure",
                "agent": "preprocessing_agent",
                "description": f"Clean and prepare PDB file: {', '.join(preprocessing_tasks) if preprocessing_tasks else 'validate structure'}",
                "inputs": {
                    "raw_pdb": pdb_path,
                    "component_selection": component_selection,
                    "tasks": preprocessing_tasks
                },
                "expected_outputs": ["cleaned_pdb", "preprocessing_report"],
                "dependencies": [],
                "tools": ["pdb_fixer", "hydrogen_adder", "structure_validator"],
                "type": "automated"
            }
            plan_steps.append(preprocess_step)
            logger.info(f"  Step {step_number}: Preprocessing with tasks: {preprocessing_tasks}")
            step_number += 1
        
        # Step 2: Simulation Setup (topology and coordinates)
        if not state.get("coordinates"):
            setup_step = {
                "step_number": step_number,
                "name": "Setup MD Simulation Files",
                "agent": "setup_agent",
                "description": "Generate topology, add solvent, ions, and create coordinate files",
                "inputs": {
                    "cleaned_pdb": "output from Step 1" if plan_steps else pdb_path,
                    "force_field": state.get("force_field", "amber99sb-ildn"),
                    "water_model": state.get("water_model", "tip3p"),
                    "component_selection": component_selection
                },
                "expected_outputs": ["topology", "coordinates", "mdp_files", "setup_report"],
                "dependencies": [1] if plan_steps else [],
                "tools": ["topology_builder", "solvator", "ion_adder", "mdp_generator"],
                "type": "automated"
            }
            plan_steps.append(setup_step)
            logger.info(f"  Step {step_number}: Simulation setup")
            step_number += 1
        
        # Step 3: HPC Submission (if requested in goal)
        goal_lower = structured_prompt.lower()
        if "run" in goal_lower or "execute" in goal_lower or "simulate" in goal_lower:
            hpc_step = {
                "step_number": step_number,
                "name": "Submit MD Simulation to HPC",
                "agent": "hpc_agent",
                "description": "Submit GROMACS simulation job to HPC cluster",
                "inputs": {
                    "topology": "output from Step 2",
                    "coordinates": "output from Step 2",
                    "mdp_files": "output from Step 2",
                    "engine": state.get("md_engine", "gromacs")
                },
                "expected_outputs": ["job_id", "job_status", "trajectory_path"],
                "dependencies": [step_number - 1] if plan_steps else [],
                "tools": ["job_script_generator", "slurm_submitter"],
                "type": "automated"
            }
            plan_steps.append(hpc_step)
            logger.info(f"  Step {step_number}: HPC submission")
            step_number += 1
        
        # Step 4: Analysis (if requested)
        if "analyz" in goal_lower or "rmsd" in goal_lower or "rmsf" in goal_lower:
            analysis_step = {
                "step_number": step_number,
                "name": "Analyze Simulation Results",
                "agent": "analysis_agent",
                "description": "Perform trajectory analysis (RMSD, RMSF, etc.)",
                "inputs": {
                    "trajectory": "output from Step 3",
                    "topology": "output from Step 2"
                },
                "expected_outputs": ["analysis_results", "figures"],
                "dependencies": [step_number - 1] if plan_steps else [],
                "tools": ["mdanalysis", "plotting_tools"],
                "type": "automated"
            }
            plan_steps.append(analysis_step)
            logger.info(f"  Step {step_number}: Analysis")
            step_number += 1
        
        # Build complete plan
        plan = {
            "title": f"MD Workflow: {component_selection}",
            "summary": f"Structured plan with {len(plan_steps)} steps based on PDB analysis",
            "method": "analysis_based",
            "pdb_file": pdb_path,
            "pdb_analysis": {
                "total_atoms": pdb_analysis.get("total_atoms", 0),
                "has_protein": pdb_analysis.get("protein", {}).get("present", False),
                "has_ligand": pdb_analysis.get("ligands", {}).get("present", False),
                "component_selection": component_selection
            },
            "steps": plan_steps
        }
        
        logger.info(f"PLANNER: Plan complete with {len(plan_steps)} dependency-aware steps")
        return plan
    
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
