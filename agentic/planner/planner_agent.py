"""
MD Workflow Planner Agent

Creates detailed execution plans by analyzing user goals, available resources,
and workflow capabilities. Communicates iteratively with supervisor and requests
programmer assistance for script generation.
"""
import logging
import yaml
import os
from typing import Dict, Any, Optional, List
from ..state import MDState
from ..llm import LLMClient
from ..utils import log_supervisor_routing

logger = logging.getLogger(__name__)


class MDPlanner:
    """
    Planner agent that creates detailed execution plans using LLM reasoning.
    Iteratively communicates with supervisor and coordinates with programmer
    for script generation.
    """
    
    def __init__(self, llm_client: LLMClient, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required")
        
        self.llm = llm_client
        self.config_path = config_path or os.path.join(
            os.path.dirname(__file__), "config.yaml"
        )
        
        # Load planner configuration
        self.config = self._load_config()
        self.knowledge_resources = self._load_knowledge_resources()
        
        logger.info("MD Planner initialized with knowledge resources")
    
    def _load_config(self) -> Dict[str, Any]:
        """Load planner configuration from YAML."""
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f) or {}
        else:
            logger.warning(f"Config file {self.config_path} not found, using defaults")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Default planner configuration."""
        return {
            "planner": {
                "max_iterations": 5,
                "require_human_approval": True,
                "auto_request_scripts": True
            },
            "planning_strategy": {
                "consider_user_constraints": True,
                "optimize_for_resources": True,
                "validate_dependencies": True
            },
            "communication": {
                "iterative_approval": True,
                "provide_alternatives": True,
                "explain_reasoning": True
            }
        }
    
    def _load_knowledge_resources(self) -> Dict[str, Any]:
        """Load knowledge resources for planning."""
        knowledge_path = os.path.join(
            os.path.dirname(__file__), "knowledge_resources.yaml"
        )
        
        if os.path.exists(knowledge_path):
            with open(knowledge_path, 'r') as f:
                return yaml.safe_load(f) or {}
        else:
            logger.warning("Knowledge resources file not found, using defaults")
            return self._get_default_knowledge()
    
    def _get_default_knowledge(self) -> Dict[str, Any]:
        """Default knowledge resources."""
        return {
            "force_fields": {
                "amber99sb-ildn": {
                    "description": "AMBER force field for proteins",
                    "suitable_for": ["proteins", "peptides"],
                    "water_models": ["tip3p", "tip4p"],
                    "parameters": "amber99sb-ildn.ff"
                },
                "charmm36": {
                    "description": "CHARMM36 force field",
                    "suitable_for": ["proteins", "lipids", "carbohydrates"],
                    "water_models": ["tip3p", "tip4p", "charmm_water"],
                    "parameters": "charmm36.ff"
                },
                "opls-aa": {
                    "description": "OPLS-AA force field",
                    "suitable_for": ["small_molecules", "ligands"],
                    "water_models": ["tip4p", "spc"],
                    "parameters": "oplsaa.ff"
                }
            },
            "simulation_engines": {
                "gromacs": {
                    "description": "GROMACS MD engine",
                    "capabilities": ["dynamics", "minimization", "analysis"],
                    "typical_time": "hours_to_days",
                    "resource_requirement": "moderate_to_high"
                },
                "lammps": {
                    "description": "LAMMPS MD engine",
                    "capabilities": ["dynamics", "minimization", "crystal_growth"],
                    "typical_time": "hours_to_weeks",
                    "resource_requirement": "high"
                }
            },
            "preprocessing_steps": {
                "water_removal": {
                    "description": "Remove crystallographic water molecules",
                    "required_before": ["solvation"],
                    "skip_conditions": ["explicit_water_needed"]
                },
                "hydrogen_addition": {
                    "description": "Add missing hydrogen atoms",
                    "required_before": ["topology_generation"],
                    "skip_conditions": ["hydrogens_already_present"]
                },
                "residue_fixing": {
                    "description": "Fix missing residues and chains",
                    "required_before": ["solvation"],
                    "skip_conditions": ["structure_complete"]
                }
            },
            "analysis_tools": {
                "rmsd": {
                    "name": "Root Mean Square Deviation",
                    "description": "Measure structural stability",
                    "requires": ["trajectory", "reference_structure"]
                },
                "rmsf": {
                    "name": "Root Mean Square Fluctuation",
                    "description": "Measure per-residue flexibility",
                    "requires": ["trajectory"]
                },
                "energy_analysis": {
                    "name": "Energy Analysis",
                    "description": "Analyze system energy components",
                    "requires": ["energy_file"]
                }
            }
        }
    
    def planner_node(self, state: MDState) -> MDState:
        """
        Main planner node. Creates detailed execution plan through iterative
        communication with supervisor.
        """
        logger.info("Planner node: Creating execution plan")
        
        # Check if we have validated input from supervisor
        if not state.get("raw_pdb"):
            state["errors"].append("Planner: No validated PDB input from supervisor")
            state["next_node"] = "supervisor"
            return state
        
        # Extract planning context
        user_goal = state.get("user_goal", "")
        validated_pdb = state.get("raw_pdb")
        supervisor_reasoning = state.get("supervisor_reasoning", "")
        
        # Create initial plan
        plan = self._create_detailed_plan(
            user_goal=user_goal,
            validated_pdb=validated_pdb,
            supervisor_context=supervisor_reasoning,
            state=state
        )
        
        # Store plan in state
        state["execution_plan"] = plan
        state["plan_version"] = 1
        state["plan_awaiting_approval"] = True
        
        # Request supervisor approval
        state["next_node"] = "supervisor"
        state["supervisor_action"] = "review_plan"
        state["plan_for_review"] = {
            "title": plan.get("title"),
            "summary": plan.get("summary"),
            "steps": plan.get("steps"),
            "resource_requirements": plan.get("resource_requirements"),
            "estimated_duration": plan.get("estimated_duration"),
            "risk_assessment": plan.get("risk_assessment")
        }
        
        logger.info(f"Created execution plan with {len(plan.get('steps', []))} steps")
        log_supervisor_routing(
            state, "supervisor",
            f"Planner created detailed plan for review. Plan has {len(plan.get('steps', []))} steps"
        )
        
        return state
    
    def _create_detailed_plan(
        self, 
        user_goal: str, 
        validated_pdb: str,
        supervisor_context: str,
        state: MDState
    ) -> Dict[str, Any]:
        """Create a detailed execution plan using LLM reasoning."""
        
        # Build planning context with knowledge resources
        knowledge_summary = self._build_knowledge_summary()
        
        prompt = f"""
You are an expert MD simulation workflow planner. Create a detailed, step-by-step execution plan.

USER GOAL:
{user_goal}

VALIDATED INPUT:
- PDB File: {validated_pdb}
- Supervisor Context: {supervisor_context}

CURRENT STATE:
{self._get_planning_state_summary(state)}

AVAILABLE KNOWLEDGE & RESOURCES:
{knowledge_summary}

PLANNING REQUIREMENTS:
1. Create ordered steps with clear dependencies
2. Identify which steps require programmer-generated scripts
3. Specify resource requirements for each step
4. Include fallback options for common issues
5. Identify human review points
6. Estimate time and computational requirements

RESPONSE FORMAT:
PLAN_TITLE: [descriptive title]
PLAN_SUMMARY: [2-3 line overview]

WORKFLOW_STEPS:
Step 1: [name]
  Description: [what happens]
  Type: [manual|automated|requires_script|human_review]
  Script_Required: [yes|no] - if yes, specify type
  Dependencies: [previous steps this depends on]
  Success_Criteria: [how to verify success]
  Fallback: [what to do if fails]
  
[repeat for all steps]

RESOURCE_REQUIREMENTS:
- CPU: [cores needed]
- GPU: [required|optional|not_needed]
- Memory: [GB needed]
- Disk: [GB needed]
- Software: [required packages]

RISK_ASSESSMENT:
- Identified Risks: [list of potential issues]
- Mitigation_Strategies: [how to handle each]

ESTIMATED_DURATION: [hours/days/weeks]

PROGRAMMER_SCRIPTS_NEEDED: [list of script types needed]

HUMAN_REVIEW_POINTS: [where human approval needed]
"""
        
        response = self.llm.prompt(
            prompt,
            system="You are an expert MD simulation workflow planner with deep knowledge of molecular dynamics, computational chemistry, and HPC resource management."
        )
        
        # Parse LLM response into structured plan
        plan = self._parse_plan_response(response)
        
        # Log planning decision
        self._log_planning_decision("plan_creation", prompt, response)
        
        return plan
    
    def _parse_plan_response(self, llm_response: str) -> Dict[str, Any]:
        """Parse LLM plan response into structured format."""
        
        plan = {
            "title": "",
            "summary": "",
            "steps": [],
            "resource_requirements": {},
            "risk_assessment": {},
            "estimated_duration": "",
            "programmer_scripts": [],
            "human_review_points": [],
            "raw_response": llm_response
        }
        
        try:
            lines = llm_response.strip().split('\n')
            current_section = None
            current_step = None
            
            for line in lines:
                line_stripped = line.strip()
                
                # Parse main sections
                if line_stripped.startswith("PLAN_TITLE:"):
                    plan["title"] = line_stripped.split(":", 1)[1].strip()
                
                elif line_stripped.startswith("PLAN_SUMMARY:"):
                    plan["summary"] = line_stripped.split(":", 1)[1].strip()
                
                elif line_stripped.startswith("Step "):
                    # Save previous step
                    if current_step:
                        plan["steps"].append(current_step)
                    
                    # Start new step
                    step_num = line_stripped.split(":")[0]
                    step_name = line_stripped.split(":", 1)[1].strip() if ":" in line_stripped else ""
                    current_step = {
                        "number": step_num,
                        "name": step_name,
                        "description": "",
                        "type": "automated",
                        "script_required": False,
                        "script_type": None,
                        "dependencies": [],
                        "success_criteria": "",
                        "fallback": ""
                    }
                
                elif current_step and line.startswith("  "):
                    # Parse step details
                    detail_line = line_stripped
                    
                    if detail_line.startswith("Description:"):
                        current_step["description"] = detail_line.split(":", 1)[1].strip()
                    elif detail_line.startswith("Type:"):
                        current_step["type"] = detail_line.split(":", 1)[1].strip()
                    elif detail_line.startswith("Script_Required:"):
                        script_req = detail_line.split(":", 1)[1].strip().lower()
                        current_step["script_required"] = "yes" in script_req
                        if "yes" in script_req and "-" in detail_line:
                            current_step["script_type"] = detail_line.split("-", 1)[1].strip()
                    elif detail_line.startswith("Dependencies:"):
                        deps = detail_line.split(":", 1)[1].strip()
                        current_step["dependencies"] = [d.strip() for d in deps.split(",")]
                    elif detail_line.startswith("Success_Criteria:"):
                        current_step["success_criteria"] = detail_line.split(":", 1)[1].strip()
                    elif detail_line.startswith("Fallback:"):
                        current_step["fallback"] = detail_line.split(":", 1)[1].strip()
                
                elif line_stripped.startswith("RESOURCE_REQUIREMENTS:"):
                    current_section = "resources"
                
                elif line_stripped.startswith("RISK_ASSESSMENT:"):
                    current_section = "risk"
                
                elif line_stripped.startswith("ESTIMATED_DURATION:"):
                    plan["estimated_duration"] = line_stripped.split(":", 1)[1].strip()
                
                elif line_stripped.startswith("PROGRAMMER_SCRIPTS_NEEDED:"):
                    scripts = line_stripped.split(":", 1)[1].strip()
                    plan["programmer_scripts"] = [s.strip() for s in scripts.split(",")]
                
                elif line_stripped.startswith("HUMAN_REVIEW_POINTS:"):
                    points = line_stripped.split(":", 1)[1].strip()
                    plan["human_review_points"] = [p.strip() for p in points.split(",")]
                
                elif current_section == "resources" and "-" in line_stripped:
                    key, value = line_stripped.split("-", 1)
                    plan["resource_requirements"][key.strip()] = value.strip()
                
                elif current_section == "risk" and "-" in line_stripped:
                    key, value = line_stripped.split("-", 1)
                    if "identified_risks" not in plan["risk_assessment"]:
                        plan["risk_assessment"]["identified_risks"] = []
                    plan["risk_assessment"]["identified_risks"].append(value.strip())
            
            # Save last step
            if current_step:
                plan["steps"].append(current_step)
        
        except Exception as e:
            logger.error(f"Error parsing plan response: {e}")
            plan["parsing_error"] = str(e)
        
        return plan
    
    def _build_knowledge_summary(self) -> str:
        """Build a summary of available knowledge resources for planning."""
        
        summary = []
        
        # Force fields
        summary.append("AVAILABLE FORCE FIELDS:")
        for ff_name, ff_info in self.knowledge_resources.get("force_fields", {}).items():
            summary.append(f"  - {ff_name}: {ff_info.get('description')}")
        
        # Simulation engines
        summary.append("\nAVAILABLE SIMULATION ENGINES:")
        for engine_name, engine_info in self.knowledge_resources.get("simulation_engines", {}).items():
            summary.append(f"  - {engine_name}: {engine_info.get('description')}")
        
        # Analysis tools
        summary.append("\nAVAILABLE ANALYSIS TOOLS:")
        for tool_name, tool_info in self.knowledge_resources.get("analysis_tools", {}).items():
            summary.append(f"  - {tool_name}: {tool_info.get('description')}")
        
        return "\n".join(summary)
    
    def _get_planning_state_summary(self, state: MDState) -> str:
        """Generate planning context from current state."""
        
        items = []
        items.append(f"User Goal: {state.get('user_goal', 'Not specified')}")
        items.append(f"Input PDB: {state.get('raw_pdb', 'Not provided')}")
        items.append(f"Working Directory: {state.get('working_directory', 'Not set')}")
        
        # Add any existing configuration
        if state.get("force_field"):
            items.append(f"Force Field Preference: {state.get('force_field')}")
        if state.get("md_engine"):
            items.append(f"MD Engine: {state.get('md_engine')}")
        if state.get("water_model"):
            items.append(f"Water Model: {state.get('water_model')}")
        
        return "\n".join(items)
    
    def _log_planning_decision(self, context: str, prompt: str, response: str):
        """Log planning decisions for audit trail."""
        logger.info(f"PLANNER_{context.upper()}_PROMPT: {prompt[:200]}...")
        logger.info(f"PLANNER_{context.upper()}_RESPONSE: {response[:200]}...")
    
    def handle_supervisor_feedback(self, state: MDState) -> MDState:
        """
        Handle supervisor feedback on the plan and request modifications
        or proceed with programmer for script generation.
        """
        feedback = state.get("supervisor_feedback", "")
        plan = state.get("execution_plan", {})
        
        if not feedback:
            logger.warning("No supervisor feedback provided")
            return state
        
        # Check if plan is approved
        if "approved" in feedback.lower():
            logger.info("Plan approved by supervisor")
            state["plan_approved"] = True
            
            # If scripts are needed, route to programmer; otherwise to preprocess
            if state.get("execution_plan", {}).get("programmer_scripts"):
                state["next_node"] = "programmer"
                log_supervisor_routing(
                    state, "programmer",
                    f"Plan approved. Routing to programmer to generate {len(state['execution_plan']['programmer_scripts'])} scripts"
                )
            else:
                state["next_node"] = "preprocess"
                log_supervisor_routing(state, "preprocess", "Plan approved, no scripts needed. Starting preprocessing.")
            
            return state
        
        # Check if modifications requested
        if "modify" in feedback.lower() or "revise" in feedback.lower():
            logger.info("Supervisor requested plan modifications")
            
            # Revise plan based on feedback
            revised_plan = self._revise_plan_from_feedback(plan, feedback, state)
            
            state["execution_plan"] = revised_plan
            state["plan_version"] = state.get("plan_version", 1) + 1
            state["plan_awaiting_approval"] = True
            state["next_node"] = "supervisor"
            state["supervisor_action"] = "review_plan"
            
            logger.info(f"Plan revised to version {state['plan_version']}")
            return state
        
        # Check if rejected
        if "reject" in feedback.lower() or "cancel" in feedback.lower():
            logger.error("Supervisor rejected the plan")
            state["errors"].append("Supervisor rejected the execution plan")
            state["next_node"] = "supervisor"
            return state
        
        # Default: treat as approval
        state["plan_approved"] = True
        if state.get("execution_plan", {}).get("programmer_scripts"):
            state["next_node"] = "programmer"
        else:
            state["next_node"] = "preprocess"
        
        return state
    
    def _revise_plan_from_feedback(
        self, 
        current_plan: Dict[str, Any],
        feedback: str,
        state: MDState
    ) -> Dict[str, Any]:
        """Revise plan based on supervisor feedback."""
        
        prompt = f"""
The supervisor has reviewed the execution plan and provided feedback.
Create a revised plan addressing their concerns.

CURRENT PLAN SUMMARY:
Title: {current_plan.get('title')}
Steps: {len(current_plan.get('steps', []))} steps
Duration: {current_plan.get('estimated_duration')}

SUPERVISOR FEEDBACK:
{feedback}

Create a revised plan addressing the feedback. Use the same format as before but focus on the areas of concern.
"""
        
        response = self.llm.prompt(
            prompt,
            system="You are an expert MD simulation planner revising a plan based on supervisor feedback."
        )
        
        revised_plan = self._parse_plan_response(response)
        revised_plan["revision_feedback"] = feedback
        
        return revised_plan