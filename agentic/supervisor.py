"""
LLM-Powered MD Workflow Supervisor

This supervisor uses LLM reasoning to understand complex user prompts and make
intelligent routing decisions to field-specific agents.
"""
import logging
import yaml
import os
from typing import Any, Dict, List, Optional, Tuple
from .state import MDState
from .utils import log_supervisor_routing
from .llm import LLMClient
from .planner import MDPlanner

logger = logging.getLogger(__name__)

class MDSupervisor:
    """
    LLM-powered supervisor that understands complex user requests and routes
    to appropriate field-specific agents based on intelligent analysis.
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None, config_path: Optional[str] = None):
        if llm_client is None:
            raise ValueError("llm_client is required. Pass LLMClient from main script.")
        self.llm = llm_client
        
        # Initialize planner (programmer initialized by planner)
        self.planner = MDPlanner(llm_client=self.llm)
        
        # Load agent registry and configuration
        if config_path is None:
            config_path = os.path.join(os.path.dirname(__file__), "configs", "intelligent_supervisor.yaml")
        
        # Load config if exists, otherwise use defaults
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                self.config = yaml.safe_load(f)
            self.agents_registry = self.config.get('agents', {})
            self.workflow_config = self.config.get('workflow', {})
            self.supervisor_config = self.config.get('supervisor', {})
        else:
            logger.warning(f"Config file {config_path} not found, using default configuration")
            self._setup_default_config()
        
        # Default configuration for compatibility
        self.default_config = {
            "md_engine": "gromacs",
            "force_field": "amber99sb-ildn", 
            "water_model": "tip3p",
            "human_in_loop": True
        }
        
        logger.info(f"MD Supervisor initialized with {len(self.agents_registry)} available agents")
    
    def _setup_default_config(self):
        """Setup default configuration when config file is not found."""
        self.agents_registry = {
            "preprocessing": {
                "name": "PDB Preprocessor",
                "description": "Clean and prepare PDB files for simulation",
                "capabilities": ["remove_waters", "fix_residues", "add_hydrogens"],
                "input_requirements": ["raw_pdb"],
                "output_provides": ["cleaned_pdb"],
                "skip_conditions": ["pdb_already_cleaned", "user_says_preprocessed"]
            },
            "setup": {
                "name": "Simulation Setup",
                "description": "Prepare MD simulation files and parameters", 
                "capabilities": ["create_topology", "solvate_system", "add_ions"],
                "input_requirements": ["cleaned_pdb"],
                "output_provides": ["topology", "coordinates"],
                "skip_conditions": ["simulation_files_exist", "user_provides_setup"]
            },
            "hpc": {
                "name": "HPC Execution",
                "description": "Execute MD simulations on high-performance computing systems",
                "capabilities": ["submit_jobs", "monitor_progress", "retrieve_results"],
                "input_requirements": ["topology", "coordinates"],
                "output_provides": ["trajectory", "energy_data"],
                "skip_conditions": ["simulation_complete", "user_provides_trajectory"]
            },
            "analysis": {
                "name": "Trajectory Analysis",
                "description": "Analyze MD simulation results and generate insights",
                "capabilities": ["rmsd_analysis", "rmsf_analysis", "energy_analysis"],
                "input_requirements": ["trajectory", "topology"],
                "output_provides": ["analysis_results", "plots"],
                "skip_conditions": ["analysis_complete"]
            }
        }
        
        self.workflow_config = {
            "default_pipeline": ["preprocessing", "setup", "hpc", "analysis"],
            "entry_points": ["preprocessing", "analysis"]
        }
        
        self.supervisor_config = {
            "llm_config": {
                "system_prompt": "You are an expert MD workflow supervisor."
            },
            "conversation": {
                "log_all_interactions": True
            }
        }
    
    def supervisor_node(self, state: MDState) -> MDState:
        """
        Intelligent routing logic using LLM reasoning when available,
        with fallback to heuristic routing for compatibility.
        """
        # Initialize defaults if not set
        if not state.get("md_engine"):
            state.update(self.default_config)
            
        if not state.get("errors"):
            state["errors"] = []
        if not state.get("warnings"):
            state["warnings"] = []
        
        # Try LLM-powered routing first
        if self.llm.available:
            return self._llm_supervisor_routing(state)
        else:
            # Fallback to heuristic routing
            logger.info("LLM not available, using heuristic routing")
            return self._heuristic_supervisor_routing(state)
    
    def _llm_supervisor_routing(self, state: MDState) -> MDState:
        """LLM-powered intelligent routing logic."""
        # First, check if we need input validation
        if not state.get("raw_pdb"):
            state["next_node"] = "input_validation"
            log_supervisor_routing(state, "input_validation", "Input validation required - PDB path not yet extracted")
            logger.info("LLM Supervisor routing to: input_validation (PDB extraction needed)")
            return state
        
        user_goal = state.get("user_goal", "")
        current_state_summary = self._get_state_summary(state)
        
        # Use LLM to determine routing
        routing_decision = self._llm_routing_decision(user_goal, current_state_summary, state)
        
        # Parse LLM response and update state
        next_agent, reasoning, agent_instructions = self._parse_routing_decision(routing_decision)
        
        state["next_node"] = next_agent
        state["supervisor_reasoning"] = reasoning
        if agent_instructions:
            state["agent_instructions"] = agent_instructions
        
        # Log the intelligent routing decision
        log_supervisor_routing(state, next_agent, f"LLM Reasoning: {reasoning}")
        
        logger.info(f"LLM Supervisor routing to: {next_agent}")
        logger.debug(f"Reasoning: {reasoning}")
        
        # After input validation, route to planner
        if not state.get("execution_plan"):
            state["next_node"] = "planner"
            log_supervisor_routing(
                state, "planner",
                "Input validated. Routing to planner to create detailed execution plan."
            )
            logger.info("LLM Supervisor routing to: planner")
            return state
        
        # Check if plan needs approval
        if state.get("plan_awaiting_approval"):
            # Plan will be reviewed and supervisor will provide feedback
            state["next_node"] = "planner"
            state["supervisor_action"] = "review_plan"
            log_supervisor_routing(
                state, "planner",
                "Supervisor reviewing plan for approval."
            )
            return state
        
        return state
    
    def _heuristic_supervisor_routing(self, state: MDState) -> MDState:
        """Original heuristic routing logic as fallback."""
        # Deterministic routing based on completion state
        if not state.get("raw_pdb"):
            state["next_node"] = "input_validation"
        elif not state.get("cleaned_pdb"):
            state["next_node"] = "preprocess"
        elif state.get("preprocessing_issues") and not self._preprocess_validated(state):
            state["next_node"] = "human_preprocess_check"
        elif not state.get("coordinates"):
            state["next_node"] = "setup"
        elif state.get("setup_issues") and not self._setup_validated(state):
            state["next_node"] = "human_setup_check"
        else:
            # For now, route to final report until HPC and analysis agents are implemented
            state["next_node"] = "final_report"
            
        # Generate routing reasoning
        reasoning = self._get_routing_reasoning(state)
        
        # Log supervisor routing decision
        log_supervisor_routing(state, state['next_node'], reasoning)
            
        logger.info(f"Supervisor routing to: {state['next_node']}")
        return state
    
    def _llm_routing_decision(self, user_goal: str, state_summary: str, state: MDState) -> str:
        """Use LLM to make intelligent routing decisions."""
        
        # Build agent capabilities summary
        agents_info = self._build_agents_summary()
        
        prompt = f"""
You are an expert MD simulation workflow supervisor. Analyze the user's request and current state to determine the next step.

USER GOAL:
{user_goal}

CURRENT STATE:
{state_summary}

AVAILABLE AGENTS:
{agents_info}

CURRENT WORKFLOW PROGRESS:
{self._get_workflow_progress(state)}

INSTRUCTIONS:
1. Analyze what the user wants to accomplish
2. Determine what stage their data/files are currently in
3. Identify which agent should handle the next step
4. Check if any steps can be intelligently skipped based on user input
5. Provide clear reasoning for your decision

Consider these scenarios:
- If user says "PDB is already preprocessed" → skip to setup
- If user provides ready simulation files → skip to HPC or analysis
- If user wants only preprocessing → route to preprocessing then stop
- If user mentions specific analysis → plan full pipeline

RESPONSE FORMAT:
NEXT_AGENT: [agent_name from: preprocessing, setup, hpc, analysis, final_report, input_validation, preprocess, human_preprocess_check, human_setup_check]
REASONING: [detailed explanation of why this agent was chosen]
INSTRUCTIONS: [any specific instructions for the chosen agent]
"""

        response = self.llm.prompt(prompt, system=self.supervisor_config.get('llm_config', {}).get('system_prompt', ''))
        
        # Log the LLM interaction
        self._log_llm_conversation("supervisor_routing", prompt, response)
        
        return response
    
    def _parse_routing_decision(self, llm_response: str) -> Tuple[str, str, Optional[str]]:
        """Parse LLM routing response into structured components."""
        
        next_agent = "input_validation"  # Default fallback
        reasoning = "LLM parsing failed, using default routing"
        instructions = None
        
        try:
            lines = llm_response.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                
                # Handle both markdown and plain text formats
                if line.startswith("NEXT_AGENT:") or line.startswith("**NEXT_AGENT:**"):
                    next_agent = line.split(":", 1)[1].strip().replace("*", "")
                elif line.startswith("REASONING:") or line.startswith("**REASONING:**"):
                    reasoning = line.split(":", 1)[1].strip().replace("*", "")
                elif line.startswith("INSTRUCTIONS:") or line.startswith("**INSTRUCTIONS:**"):
                    instructions = line.split(":", 1)[1].strip().replace("*", "")
            
            # Clean up agent name - remove common variations
            next_agent = next_agent.replace("Agent", "").replace("PDB ", "").replace("Preprocessing", "preprocessing").strip()
            
            # Validate agent name and map to compatible names
            valid_agents = list(self.agents_registry.keys()) + [
                "final_report", "input_validation", "preprocess", 
                "human_preprocess_check", "human_setup_check"
            ]
            
            # Map agent names to existing workflow names
            agent_mapping = {
                "preprocessing": "preprocess",  # Map to existing node name
                "setup": "setup",
                "hpc": "hpc", 
                "analysis": "analysis"
            }
            
            # If LLM suggests "preprocessing", map to "preprocess"
            if next_agent.lower() in ["preprocessing", "preprocess"]:
                next_agent = "preprocess"
            elif next_agent.lower() == "setup":
                next_agent = "setup"
            elif next_agent.lower() in ["hpc", "hpc execution"]:
                next_agent = "hpc"
            elif next_agent.lower() == "analysis":
                next_agent = "analysis"
            
            # Final validation
            if next_agent not in valid_agents:
                logger.warning(f"LLM suggested invalid agent '{next_agent}', defaulting to input_validation")
                next_agent = "input_validation"
                reasoning = f"LLM suggested invalid agent, defaulting to input validation. Original response: {llm_response[:100]}..."
                
        except Exception as e:
            logger.error(f"Error parsing LLM routing decision: {e}")
            reasoning = f"Error parsing LLM response: {e}"
            
        return next_agent, reasoning, instructions
    
    def _build_agents_summary(self) -> str:
        """Build a summary of available agents for LLM context."""
        
        agents_summary = []
        for agent_id, agent_config in self.agents_registry.items():
            summary = f"""
{agent_id.upper()}:
- Name: {agent_config['name']}
- Purpose: {agent_config['description']}
- Capabilities: {', '.join(agent_config['capabilities'])}
- Requires: {', '.join(agent_config['input_requirements'])}
- Produces: {', '.join(agent_config['output_provides'])}
- Skip if: {', '.join(agent_config['skip_conditions'])}
"""
            agents_summary.append(summary)
        
        return '\n'.join(agents_summary)
    
    def _get_state_summary(self, state: MDState) -> str:
        """Generate a human-readable summary of the current workflow state."""
        
        state_items = []
        
        # Check key state variables
        state_vars = [
            ("raw_pdb", "Input PDB file"),
            ("cleaned_pdb", "Processed PDB"),
            ("topology", "System topology"),
            ("coordinates", "Simulation coordinates"),
            ("job_id", "HPC job"),
            ("analysis_results", "Analysis data")
        ]
        
        for var, description in state_vars:
            value = state.get(var)
            if value:
                state_items.append(f"✅ {description}: {value}")
            else:
                state_items.append(f"❌ {description}: Not set")
        
        # Add error and warning counts
        errors = state.get("errors", [])
        warnings = state.get("warnings", [])
        
        if errors:
            state_items.append(f"⚠️ Errors: {len(errors)} issues")
        if warnings:
            state_items.append(f"⚠️ Warnings: {len(warnings)} issues")
        
        return '\n'.join(state_items)
    
    def _get_workflow_progress(self, state: MDState) -> str:
        """Determine how far through the pipeline we are."""
        
        default_pipeline = self.workflow_config.get('default_pipeline', ['preprocessing', 'setup', 'hpc', 'analysis'])
        completed_steps = []
        
        if state.get("raw_pdb"):
            completed_steps.append("input")
        if state.get("cleaned_pdb"):
            completed_steps.append("preprocessing")
        if state.get("coordinates"):
            completed_steps.append("setup")
        if state.get("job_id"):
            completed_steps.append("hpc")
        if state.get("analysis_results"):
            completed_steps.append("analysis")
        
        total_steps = len(default_pipeline)
        progress_percent = (len(completed_steps) / total_steps) * 100 if total_steps > 0 else 0
        
        return f"Completed: {completed_steps} ({progress_percent:.0f}% through pipeline)"
    
    def _log_llm_conversation(self, context: str, prompt: str, response: str):
        """Log LLM conversations for supervisor decisions."""
        
        if self.supervisor_config.get('conversation', {}).get('log_all_interactions', False):
            logger.info(f"LLM_SUPERVISOR_{context.upper()}_PROMPT: {prompt[:200]}...")
            logger.info(f"LLM_SUPERVISOR_{context.upper()}_RESPONSE: {response[:200]}...")

    def input_validation_node(self, state: MDState) -> MDState:
        """Enhanced input validation using LLM understanding when available."""
        user_goal = state.get("user_goal", "")
        
        # Try LLM-powered analysis first
        if self.llm.available:
            # Use LLM to extract and validate input information
            validation_result = self._llm_input_analysis(user_goal)
            
            # Parse LLM analysis
            extracted_info = self._parse_input_analysis(validation_result)
            
            # Update state with extracted information
            for key, value in extracted_info.items():
                if value:
                    state[key] = value
        else:
            # Fallback to original extraction logic
            pdb_path = self._extract_pdb_path(user_goal)
            
            if pdb_path:
                state["raw_pdb"] = pdb_path
                
                # Set working directory intelligently
                import os
                pdb_dir = os.path.dirname(pdb_path)
                
                if pdb_dir and pdb_dir != ".":
                    state["working_directory"] = pdb_dir
                    log_supervisor_routing(state, "input_validation", 
                        f"Extracted PDB: {pdb_path}, Working directory set to: {pdb_dir}")
                else:
                    state["working_directory"] = "."
                    log_supervisor_routing(state, "input_validation", 
                        f"Extracted PDB: {pdb_path}, Using current directory as working directory")
                        
                # Check if file exists
                if os.path.isabs(pdb_path) or "/" in pdb_path:
                    if not os.path.exists(pdb_path):
                        state["warnings"].append(f"PDB file {pdb_path} does not exist yet")
                    else:
                        log_supervisor_routing(state, "input_validation", 
                            f"Confirmed PDB file exists: {pdb_path}")
            else:
                state["errors"].append("Could not extract PDB path from user goal. Please specify a .pdb file path.")
        
        state["next_node"] = "supervisor"
        return state
    
    def _llm_input_analysis(self, user_goal: str) -> str:
        """Use LLM to analyze and extract information from user input."""
        
        prompt = f"""
Analyze the following user request for MD simulation and extract key information:

USER REQUEST:
{user_goal}

Extract and identify:
1. PDB file paths or protein identifiers
2. Working directory locations
3. Simulation parameters (force field, water model, etc.)
4. What stage the user's data is in (raw PDB, preprocessed, ready for simulation, etc.)
5. What the user ultimately wants to accomplish

RESPONSE FORMAT:
PDB_PATH: [file path if found, or "not_specified"]
WORKING_DIR: [directory path if found, or "not_specified"]
FORCE_FIELD: [force field if specified, or "not_specified"]
WATER_MODEL: [water model if specified, or "not_specified"]
DATA_STAGE: [raw_pdb|preprocessed|setup_complete|simulation_complete]
USER_INTENT: [brief description of what user wants]
VALIDATION_STATUS: [valid|needs_clarification]
ISSUES: [list any problems or missing information]
"""
        
        response = self.llm.prompt(prompt)
        self._log_llm_conversation("input_validation", prompt, response)
        
        return response
    
    def _parse_input_analysis(self, llm_response: str) -> Dict[str, Any]:
        """Parse LLM input analysis into structured data."""
        
        extracted = {}
        
        try:
            lines = llm_response.strip().split('\n')
            
            for line in lines:
                line = line.strip()
                if ':' not in line:
                    continue
                    
                key, value = line.split(':', 1)
                key = key.strip().lower()
                value = value.strip()
                
                if value.lower() in ['not_specified', 'not specified', 'none']:
                    continue
                    
                # Map LLM output to state variables (handle both uppercase and lowercase)
                mapping = {
                    'pdb_path': 'raw_pdb',
                    'pdb_file': 'raw_pdb',
                    'working_dir': 'working_directory',
                    'working_directory': 'working_directory',
                    'force_field': 'force_field',
                    'water_model': 'water_model',
                    'user_intent': 'user_intent_analysis',
                    'data_stage': 'data_stage'
                }
                
                state_key = mapping.get(key, key)
                # For mapped keys, use the mapped state key; otherwise keep as is
                if key in mapping:
                    extracted[state_key] = value
                elif state_key == key and key not in mapping:
                    # Only add unmapped keys if they're not in the mapping
                    extracted[state_key] = value
                
        except Exception as e:
            logger.error(f"Error parsing input analysis: {e}")
        
        return extracted
    
    
    def _get_routing_reasoning(self, state: MDState) -> str:
        """Generate human-readable reasoning for routing decision."""
        if not state.get("raw_pdb"):
            return "No input PDB file found, need to validate input"
        elif not state.get("cleaned_pdb"):
            return "Raw PDB needs preprocessing (cleaning, fixing)"
        elif state.get("preprocessing_issues") and not self._preprocess_validated(state):
            return "Preprocessing found issues requiring human review"
        elif not state.get("coordinates"):
            return "Need to setup simulation system (solvation, ions)"
        elif state.get("setup_issues") and not self._setup_validated(state):
            return "Setup found issues requiring human review"
        else:
            return "All workflow steps completed, generating final report"
    
    def _preprocess_validated(self, state: MDState) -> bool:
        """Check if preprocessing issues have been addressed."""
        return state.get("human_feedback") and "preprocess_approved" in str(state.get("human_feedback", ""))
    
    def _setup_validated(self, state: MDState) -> bool:
        """Check if setup issues have been addressed.""" 
        return state.get("human_feedback") and "setup_approved" in str(state.get("human_feedback", ""))

    def _extract_pdb_path(self, user_goal: str) -> str:
        """Extract PDB file path from user goal with multiple extraction strategies."""
        import re
        import os
        
        # Strategy 1: Look for explicit file paths (with directories)
        path_patterns = [
            r'([^\s]+/[^\s]*\.pdb)',  # Paths with directories
            r'(\./[^\s]*\.pdb)',       # Relative paths starting with ./
            r'(\.\./[^\s]*\.pdb)',     # Relative paths starting with ../
            r'([~/][^\s]*\.pdb)',      # Home directory paths
            r'([A-Za-z]:[\\\\/][^\s]*\.pdb)',  # Windows absolute paths
        ]
        
        for pattern in path_patterns:
            match = re.search(pattern, user_goal)
            if match:
                return match.group(1)
        
        # Strategy 2: Look for any PDB filename (fallback)
        simple_match = re.search(r'(\S+\.pdb)', user_goal)
        if simple_match:
            return simple_match.group(1)
            
        # Strategy 3: Look for common PDB naming patterns
        protein_patterns = [
            r'protein\s+([A-Za-z0-9_-]+)',
            r'PDB\s+([A-Za-z0-9_-]+)',
            r'structure\s+([A-Za-z0-9_-]+)',
        ]
        
        for pattern in protein_patterns:
            match = re.search(pattern, user_goal, re.IGNORECASE)
            if match:
                protein_name = match.group(1)
                if not protein_name.endswith('.pdb'):
                    protein_name += '.pdb'
                return protein_name
        
        return None
