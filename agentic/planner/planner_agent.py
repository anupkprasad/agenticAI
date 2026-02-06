"""
MD Workflow Planner Agent - LLM-Powered with Dynamic Tools & Knowledge

Creates execution plans with access to:
- Dynamic tool discovery from all agents
- Knowledge base (research papers, protocols, manuals)
- Field-specific expertise for detailed planning
"""
import logging
import yaml
import os
from typing import Dict, Any, Optional, List
from ..state import MDState
from ..llm import LLMClient
from ..utils import log_supervisor_routing, log_llm_interaction
from ..programmer import MDProgrammer
from .tools_registry import get_tools_registry
from .knowledge_loader import get_knowledge_loader

logger = logging.getLogger(__name__)


class MDPlanner:
    """
    LLM-powered planner with dynamic tools and knowledge access.
    
    Creates detailed execution plans by:
    1. Discovering available tools from all agents dynamically
    2. Loading relevant knowledge from knowledge base
    3. Using LLM to create context-aware execution plans
    4. Providing high-level plans for field agents to structure
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
        
        # Initialize tools registry (dynamic tool discovery)
        logger.info("Initializing tools registry...")
        self.tools_registry = get_tools_registry()
        
        # Initialize knowledge loader
        logger.info("Loading knowledge base...")
        self.knowledge_loader = get_knowledge_loader()
        
        logger.info(f"MD Planner initialized with {len(self.tools_registry.tools)} tools and "
                   f"{len(self.knowledge_loader.knowledge_docs)} knowledge documents")
    
    def _get_tools_context(self, agent_name: Optional[str] = None) -> str:
        """
        Get formatted tools context for LLM.
        
        Args:
            agent_name: If specified, only get tools for this agent
            
        Returns:
            Formatted tools description string
        """
        return self.tools_registry.get_tools_for_planner(agent_name)
    
    def _get_knowledge_context(self, 
                               category: Optional[str] = None,
                               max_chars: int = 8000) -> str:
        """
        Get formatted knowledge context for LLM.
        
        Args:
            category: If specified, only get knowledge from this category
            max_chars: Maximum characters to include in context
            
        Returns:
            Formatted knowledge string
        """
        return self.knowledge_loader.get_knowledge_for_planner(category, max_chars)
    
    def _get_knowledge_summary(self) -> str:
        """Get knowledge files summary (for logging only, not full content)."""
        return self.knowledge_loader.get_knowledge_files_summary()
    
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
        
        Uses dynamic tools knowledge and domain knowledge to create comprehensive plans.
        """
        logger.info("PLANNER: Creating plan with dynamic tools and knowledge")
        
        # Get available tools context
        tools_context = self._get_tools_context()
        
        # Get relevant knowledge (protocols and force fields)
        knowledge_context = self._get_knowledge_context(max_chars=6000)
        
        # Build LLM prompt with all context
        planning_prompt = self._build_planning_prompt(
            structured_prompt,
            pdb_path,
            pdb_analysis,
            component_selection,
            state,
            tools_context,
            knowledge_context
        )
        
        # Call LLM to create plan
        try:
            logger.info("PLANNER: Calling LLM to create execution plan...")
            response = self.llm.prompt(
                prompt=planning_prompt,
                temperature=0.2,
                max_tokens=2000
            )
            
            log_llm_interaction(
                agent_name="planner.execution_planning",
                prompt=planning_prompt,
                response=response
            )
            
            # Parse LLM response into structured plan
            plan = self._parse_llm_plan_response(response, state)
            
        except Exception as e:
            logger.error(f"PLANNER: LLM planning failed: {e}", exc_info=True)
            logger.warning("PLANNER: Falling back to template-based planning")
            plan = self._create_fallback_plan(
                structured_prompt, pdb_path, pdb_analysis, component_selection, state
            )
        
        return plan
    
    def _build_planning_prompt(
        self,
        structured_prompt: str,
        pdb_path: str,
        pdb_analysis: Dict[str, Any],
        component_selection: Dict[str, Any],
        state: MDState,
        tools_context: str,
        knowledge_context: str
    ) -> str:
        """Build comprehensive planning prompt for detailed natural language plans."""
        
        # Extract key information
        force_field = state.get("force_field", "amber99sb-ildn")
        water_model = state.get("water_model", "tip3p")
        components = pdb_analysis.get("components_available", {})
        
        prompt = f"""You are an expert MD simulation workflow planner with deep knowledge of molecular dynamics protocols, force fields, and computational tools.

**USER GOAL:**
{structured_prompt}

**PDB STRUCTURE ANALYSIS:**
- File: {pdb_path}
- Total atoms: {pdb_analysis.get('total_atoms', 'unknown')}
- Total residues: {pdb_analysis.get('total_residues', 'unknown')}
- Components present:
  - Protein: {'Yes' if components.get('protein', False) else 'No'}
  - Ligand: {'Yes' if components.get('ligand', False) else 'No'}
  - Water: {'Yes' if components.get('water', False) else 'No'}
  - Ions: {'Yes' if components.get('ions', False) else 'No'}
  - Hydrogens: {'Yes' if components.get('hydrogens', False) else 'No'}

**USER'S COMPONENT SELECTION:**
- Protein: {'Include' if component_selection.get('protein', False) else 'Exclude'}
- Ligand: {'Include' if component_selection.get('ligand', False) else 'Exclude'}
- Water: {'Include' if component_selection.get('water', False) else 'Exclude'}
- Ions: {'Include' if component_selection.get('ions', False) else 'Exclude'}
- Specific chains: {component_selection.get('specific_chains', 'All chains')}

**SIMULATION PARAMETERS:**
- Force field: {force_field}
- Water model: {water_model}

**AVAILABLE TOOLS BY AGENT:**
{tools_context}

**DOMAIN KNOWLEDGE & BEST PRACTICES:**
[Full knowledge content provided to LLM - {len(knowledge_context)} chars]

Knowledge Files Available:
{self._get_knowledge_summary()}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**YOUR TASK:**
Create a DETAILED, COMPREHENSIVE execution plan in natural language. This plan will be given to specialized field agents (preprocessing, setup, HPC, analysis) who will create their own structured tool execution plans.

Your plan should be:
1. **High-level** - Describe WHAT needs to be done, not exact tool commands
2. **Detailed** - Provide enough context for agents to understand requirements
3. **Sequential** - Clearly indicate execution order and dependencies
4. **Rationale-driven** - Explain WHY each step is important
5. **Best-practice aware** - Reference protocols and domain knowledge
6. **Practical** - Consider the available tools and common pitfalls

**PLAN STRUCTURE (Natural Language, Detailed):**

## 1. Goal Interpretation
[Clearly state what the user wants to accomplish and any constraints]

## 2. PDB Analysis Summary
[Summarize the structure's composition and what needs to be prepared]

## 3. Agent Assignments & Detailed Instructions

### Preprocessing Agent (if needed)
**Objective:** [What preprocessing must achieve]
**Detailed Instructions:**
- [Specific tasks in detail, e.g., "Remove all water molecules and heteroatoms except the ATP ligand in chain I"]
- [Reference why, e.g., "to isolate the protein-ligand complex for force field topology generation"]
**Available Tools:** [List relevant tools they can use]
**Critical Considerations:** [Things they must watch for]
**Expected Output:** [What files/data this produces]

### Setup Agent (if needed)
**Objective:** [What setup must achieve]
**Detailed Instructions:**
- [E.g., "Generate topology using AMBER99SB-ILDN for the protein and GAFF parameters for the ATP ligand"]
- [E.g., "Create a cubic water box with 1.0 nm minimum distance, solvate with TIP3P water"]
**Available Tools:** [List relevant tools]
**Critical Considerations:** [E.g., "Ensure ligand parameters are compatible with protein force field"]
**Expected Output:** [topology files, coordinate files, mdp files]

### HPC Agent (if running simulation)
[Similar detailed structure...]

### Analysis Agent (if analyzing)
[Similar detailed structure...]

## 4. Execution Sequence
[Describe step-by-step flow in prose, with dependencies clearly stated]

## 5. Expected Outcomes
[What files and data should exist after each agent completes]

## 6. Potential Issues & Solutions
[Known challenges and how agents should handle them]

## 7. Recommendations
[Best practices and optional optimizations]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Write the detailed execution plan now:"""
        
        return prompt
    
    def _parse_llm_plan_response(self, response: str, state: MDState) -> Dict[str, Any]:
        """Parse LLM natural language response into plan structure.
        
        Extracts key information from prose plans:
        - Which agents are assigned tasks
        - Execution sequence/dependencies
        - Key objectives and considerations
        
        Field agents will receive the full natural language plan and create
        their own detailed tool execution plans.
        """
        import re
        
        logger.info("PLANNER: Parsing natural language execution plan")
        
        # Extract which agents are mentioned
        agent_mentions = {
            "preprocessing_agent": bool(re.search(r'(?i)preprocessing\s+agent', response)),
            "setup_agent": bool(re.search(r'(?i)setup\s+agent', response)),
            "hpc_agent": bool(re.search(r'(?i)hpc\s+agent', response)),
            "analysis_agent": bool(re.search(r'(?i)analysis\s+agent', response))
        }
        
        # Build lightweight plan structure for routing
        steps = []
        step_num = 1
        
        for agent_name, is_mentioned in agent_mentions.items():
            if is_mentioned:
                steps.append({
                    "step_number": step_num,
                    "agent": agent_name,
                    "type": "natural_language",  # Signal to field agents
                    "dependencies": [step_num - 1] if step_num > 1 else []
                })
                step_num += 1
        
        plan = {
            "title": "Detailed Natural Language Execution Plan",
            "format": "natural_language",
            "full_plan": response,  # Full prose plan for field agents
            "agent_sequence": [s["agent"] for s in steps],
            "steps": steps
        }
        
        logger.info(f"PLANNER: Detected {len(steps)} agents in execution sequence: {plan['agent_sequence']}")
        return plan
    
    def _create_fallback_plan(
        self,
        structured_prompt: str,
        pdb_path: str,
        pdb_analysis: Dict[str, Any],
        component_selection: Dict[str, Any],
        state: MDState
    ) -> Dict[str, Any]:
        """
        Fallback template-based planning when LLM is unavailable.
        
        This creates dependency-aware plans with clear inputs/outputs for each step.
        """
        logger.info("PLANNER: Creating fallback plan from PDB analysis")
        
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
