"""
Simulation Setup Agent - Orchestrates GROMACS simulation system preparation
Follows same workflow pattern as preprocessing_agent: LLM planning → tool execution
"""
import logging
import json
import yaml
import os
import shutil
from typing import Dict, Any, Optional
from pathlib import Path

from ..state import MDState
from ..llm import LLMClient
from ..utils import (
    log_agent_start, log_llm_interaction, log_agent_action, 
    log_file_operation, log_agent_completion, log_error,
    SecureFileManager
)
from .schemas import (
    SimSetupPlan, SimSetupStep, 
    SimSetupResult, SimSetupAgentInput, SimSetupAgentOutput
)
from .tools import SimulationSetupToolExecutor, get_tool_metadata

logger = logging.getLogger(__name__)


class SimulationSetupAgent:
    """
    LLM-powered simulation setup agent - orchestrates GROMACS system preparation workflow
    Delegates tool execution to SimulationSetupToolExecutor from tools.py
    """
    
    def __init__(self, llm_client: Optional[LLMClient] = None, config_path: Optional[str] = None):
        """
        Initialize simulation setup agent
        
        Args:
            llm_client: LLM client for intelligent planning
            config_path: Path to config.yaml (defaults to same directory)
        """
        if llm_client is None:
            self.llm = LLMClient("gpt-oss:20b")
        else:
            self.llm = llm_client
        
        self.tool_executor = None
        self.file_manager = None  # Initialized per execution for state-specific file registry
        self.config = self._load_config(config_path)
        
    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """Load setup configuration from YAML"""
        if config_path is None:
            config_path = Path(__file__).parent / "config.yaml"
        
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.warning(f"Failed to load config from {config_path}: {e}")
            return {}
    
    def setup_node(self, state: MDState) -> MDState:
        """
        Main setup node - entry point from workflow
        Orchestrates the entire simulation setup pipeline
        """
        # Check if we have planner instructions
        execution_plan = state.get("execution_plan", {})
        has_planner_instructions = execution_plan.get("format") == "natural_language"
        
        input_summary = {
            "cleaned_pdb": state.get("cleaned_pdb"),
            "force_field": state.get("force_field"),
            "water_model": state.get("water_model")
        }
        
        if has_planner_instructions:
            # Prefer pre-extracted instructions from supervisor (avoids duplication)
            setup_section = state.get("setup_instructions")
            
            if not setup_section:
                # Fallback: Extract from full plan if supervisor didn't provide it
                full_plan = execution_plan.get("full_plan", "")
                setup_section = self._extract_agent_instructions(full_plan, "Simulation Setup Agent")
            
            if setup_section:
                input_summary["planner_instructions"] = setup_section
            else:
                input_summary["planner_instructions"] = "[Natural language plan from planner - see above]"
        else:
            # Fallback to user goal if no planner instructions
            input_summary["user_goal"] = state.get("user_goal")
        
        log_agent_start("setup", "Simulation System Setup with LLM Tool Calling", input_summary)
        
        try:
            # Initialize secure file manager
            base_working_dir = state.get("working_directory", "working_dir")
            file_registry = state.get("file_registry", {})
            
            self.file_manager = SecureFileManager(
                working_dir=base_working_dir,
                agent_name="simsetup",
                file_registry=file_registry
            )
            
            logger.info(f"SimSetup agent directory: {self.file_manager.agent_dir}")
            
            # Get simsetup directory from file manager (ensures consistency)
            simsetup_dir = self.file_manager.agent_dir
            
            # CRITICAL: Set simsetup_directory in state BEFORE creating tool executor
            state["simsetup_directory"] = simsetup_dir
            
            self.tool_executor = SimulationSetupToolExecutor(simsetup_dir, self.config)
            
            # Copy preprocessed files from preprocess directory
            self._copy_preprocessed_files(state, simsetup_dir)
            
            # Prepare agent input from state
            agent_input = self._prepare_agent_input(state)
            
            # Run LLM-guided setup workflow
            agent_output = self._run_setup_workflow(agent_input, state)
            
            # Update state with results
            self._update_state(state, agent_output)
            
            # Determine next workflow node
            if agent_output.success:
                if state.get("human_in_loop") and agent_output.result.issues:
                    state["next_node"] = "human_setup_check"
                else:
                    state["next_node"] = "supervisor"
            else:
                state["errors"].append(f"Setup failed: {agent_output.result.report}")
                state["next_node"] = "supervisor"
            
            success = agent_output.success and len(agent_output.result.issues) == 0
            log_agent_completion("setup", "Simulation System Setup", state, success)
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Setup agent failed: {e}")
            logger.error(f"Traceback: {tb}")
            log_error("setup_agent.setup_node", e, {"state": str(state), "traceback": tb})
            state["errors"].append(f"Setup error: {str(e)}")
            state["next_node"] = "supervisor"
        
        return state
    
    def _extract_agent_instructions(self, full_plan: str, agent_name: str) -> Optional[str]:
        """
        Extract agent-specific detailed instructions from planner's natural language plan.
        
        Args:
            full_plan: Complete natural language plan from planner
            agent_name: Name of the agent section to extract (e.g., "Simulation Setup Agent")
            
        Returns:
            Extracted instructions for this specific agent, or full plan as fallback
        """
        import re
        
        # Try multiple patterns to find the agent section (in priority order)
        patterns = [
            # New standardized format: **Simulation Setup Agent:**
            rf'\*\*Simulation Setup Agent:\*\*\s*\n(.*?)(?=\n\s*\*\*(?:HPC Agent|Analysis Agent|Expected Outcomes):|$)',
            # Alternative: **Setup Agent:**
            rf'\*\*Setup Agent:\*\*\s*\n(.*?)(?=\n\s*\*\*(?:HPC Agent|Analysis Agent|Expected Outcomes):|$)',
            # With optional colon
            rf'\*\*{agent_name}\*\*:?\s*\n(.*?)(?=\n\s*\*\*[A-Z]|\Z)',
            # Markdown headings
            rf'###\s*{agent_name}.*?\n(.*?)(?=###|\Z)',
            rf'##\s*{agent_name}.*?\n(.*?)(?=##|\Z)',
            # Fuzzy match patterns (allow for variations)
            rf'\*\*(?:Simulation\s*)?Setup.*?Agent\*\*:?\s*\n(.*?)(?=\n\s*\*\*[A-Z]|\Z)',
            rf'###\s*(?:Simulation\s*)?Setup.*?Agent.*?\n(.*?)(?=###|\Z)',
            rf'##\s*(?:Simulation\s*)?Setup.*?Agent.*?\n(.*?)(?=##|\Z)',
            # Section number patterns
            rf'\d+\..*?(?:Simulation\s*)?Setup.*?Agent.*?\n(.*?)(?=\d+\.|\Z)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, full_plan, re.DOTALL | re.IGNORECASE)
            if match:
                instructions = match.group(1).strip()
                if len(instructions) > 50:  # Ensure we got substantial content
                    logger.info(f"Extracted {len(instructions)} chars of detailed instructions for {agent_name}")
                    return instructions
        
        # Fallback: Use full plan if no specific section found
        logger.info(f"Could not find specific section for {agent_name}, using full plan as context")
        logger.info(f"Full plan length: {len(full_plan)} chars")
        
        # Return full plan so agent still has context
        return full_plan
    
    def _copy_preprocessed_files(self, state: MDState, simsetup_dir: str):
        """Copy necessary files from preprocess directory to simsetup directory"""
        preprocess_dir = state.get("preprocess_directory")
        
        # Fallback: try to construct preprocess directory path
        if not preprocess_dir:
            base_working_dir = state.get("working_directory", "working_dir")
            preprocess_dir = str(Path(base_working_dir) / "preprocess")
            logger.info(f"preprocess_directory not in state, using fallback: {preprocess_dir}")
            
            # Check if fallback directory exists
            if not os.path.exists(preprocess_dir):
                logger.warning(f"Preprocessing directory does not exist: {preprocess_dir}")
                logger.info("Setup will use files from their current locations")
                return
        
        # Copy files using file_registry via SecureFileManager (preferred method)
        preprocess_files = [
            (file_path, metadata) 
            for file_path, metadata in self.file_manager.file_registry.items()
            if metadata.get("stage") == "preprocess" and Path(file_path).exists()
        ]
        
        copied_files = set()  # Track what we've copied to avoid duplicates
        
        if preprocess_files:
            # Copy all preprocessing files using SecureFileManager
            for file_path, metadata in preprocess_files:
                filename = Path(file_path).name
                
                if filename not in copied_files:
                    # Use secure copy (automatically registers)
                    new_path = self.file_manager.copy_file(
                        source_path=file_path,
                        dest_filename=filename,
                        file_type=metadata.get("type", "file"),
                        description=f"Copy from preprocess: {metadata.get('description', 'N/A')}"
                    )
                    
                    if new_path:
                        copied_files.add(filename)
                        
                        # Update cleaned_pdb if this is the protein component
                        if metadata.get("component") == "protein":
                            state["cleaned_pdb"] = new_path
                            logger.info(f"Updated cleaned_pdb to: {new_path}")
                        
                        file_type = metadata.get("type", "file")
                        description = metadata.get("description", "N/A")
                        logger.info(f"Copied {filename} ({file_type}) from preprocess to simsetup")
        
        # Fallback: if no file_registry, use cleaned_pdb from state
        if not copied_files:
            cleaned_pdb = state.get("cleaned_pdb")
            if cleaned_pdb and os.path.exists(cleaned_pdb):
                filename = Path(cleaned_pdb).name
                
                # Use secure copy
                new_path = self.file_manager.copy_file(
                    source_path=cleaned_pdb,
                    dest_filename=filename,
                    file_type="pdb",
                    description="From preprocessing agent (fallback)"
                )
                
                if new_path:
                    state["cleaned_pdb"] = new_path
                    logger.info(f"Copied {filename} from preprocessing (fallback method)")
    
    def _prepare_agent_input(self, state: MDState) -> SimSetupAgentInput:
        """Prepare structured input for setup from workflow state"""
        defaults = self.config.get("defaults", {})
        
        # Check if planner provided detailed instructions for this agent
        # Prefer pre-extracted instructions from supervisor
        planner_instructions = state.get("setup_instructions")
        
        if not planner_instructions:
            # Fallback: Extract from execution_plan if supervisor didn't provide it
            execution_plan = state.get("execution_plan", {})
            if execution_plan.get("format") == "natural_language":
                full_plan = execution_plan.get("full_plan", "")
                planner_instructions = self._extract_agent_instructions(full_plan, "Simulation Setup Agent")
            
        return SimSetupAgentInput(
            cleaned_pdb=state.get("cleaned_pdb", ""),
            working_directory=state.get("working_directory", "working_dir"),
            force_field=state.get("force_field", defaults.get("force_field", "amber99sb-ildn")),
            water_model=state.get("water_model", defaults.get("water_model", "tip3p")),
            temperature=state.get("temperature", defaults.get("temperature", 300.0)),
            pressure=state.get("pressure", defaults.get("pressure", 1.0)),
            user_goal=state.get("user_goal", ""),
            additional_instructions=planner_instructions
        )
    
    def _run_setup_workflow(self, agent_input: SimSetupAgentInput, 
                           state: MDState) -> SimSetupAgentOutput:
        """
        Run complete setup workflow:
        1. LLM creates intelligent plan based on system analysis
        2. Execute plan step-by-step using tools
        3. Return structured results
        """
        try:
            # Step 1: LLM analyzes system and creates plan
            plan = self._create_setup_plan(agent_input, state)
            
            log_agent_action("setup", "Generated setup plan", {
                "steps": len(plan.steps),
                "reasoning": plan.reasoning[:200]
            })
            
            # Step 2: Execute plan using tool executor
            result = self._execute_plan(agent_input, plan, state)
            
            # Step 3: Register created files using SecureFileManager
            if result.topology:
                self.file_manager.register_external_file(
                    file_path=result.topology,
                    file_type="topology",
                    description="GROMACS topology file (.top)"
                )
            
            if result.coordinates:
                self.file_manager.register_external_file(
                    file_path=result.coordinates,
                    file_type="coordinates",
                    description="GROMACS coordinate file (.gro)"
                )
            
            # Register MDP files
            for mdp_type, mdp_path in result.mdp_files.items():
                self.file_manager.register_external_file(
                    file_path=mdp_path,
                    file_type="mdp",
                    description=f"GROMACS MDP file for {mdp_type}"
                )
            
            # Step 4: Prepare supervisor update
            supervisor_update = {
                "coordinates": result.coordinates,
                "topology": result.topology,
                "mdp_files": result.mdp_files,
                "setup_report": result.report,
                "file_registry": self.file_manager.file_registry  # Use file_registry from file_manager
            }
            
            return SimSetupAgentOutput(
                success=result.success,
                plan=plan,
                result=result,
                supervisor_update=supervisor_update
            )
            
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            logger.error(f"Setup workflow failed: {e}")
            logger.error(f"Traceback: {tb}")
            return SimSetupAgentOutput(
                success=False,
                plan=SimSetupPlan(
                    reasoning=f"Error in planning: {str(e)}",
                    overview="Failed",
                    steps=[]
                ),
                result=SimSetupResult(
                    success=False,
                    report=f"Error: {str(e)}\n\nTraceback:\n{tb}",
                    issues=[str(e)],
                    warnings=[]
                ),
                supervisor_update={}
            )
    
    def _create_setup_plan(self, agent_input: SimSetupAgentInput, state: MDState) -> SimSetupPlan:
        """
        Use LLM to analyze system and create intelligent setup plan
        Falls back to template-based plan if LLM fails
        """
        # Analyze the system first
        cleaned_pdb = agent_input.cleaned_pdb
        analysis = self._analyze_system(cleaned_pdb)
        # Store for use in _execute_plan
        self._last_analysis = analysis
        
        # Build LLM prompt from config template
        prompt = self._build_planning_prompt(agent_input, analysis, state)
        
        try:
            response = self.llm.invoke([prompt])
            content = response.content or ""
            
            log_llm_interaction("setup.planning", prompt, content,
                              is_mock=hasattr(self.llm, '_is_mock_mode') and self.llm._is_mock_mode)
            
            # Parse LLM response into structured plan
            plan_dict = self._extract_plan_json(content)
            
            return SimSetupPlan(
                reasoning=plan_dict.get("reasoning", content[:500]),
                overview=plan_dict.get("overview", "Setting up GROMACS simulation system"),
                steps=[
                    SimSetupStep(
                        name=step.get("name", "unknown"),
                        description=step.get("description", ""),
                        tool_name=step.get("tool_name", ""),
                        tool_params=step.get("tool_params", {}),
                        reason=step.get("reason", "")
                    )
                    for step in plan_dict.get("steps", [])
                ],
                potential_issues=plan_dict.get("potential_issues", []),
                recommendations=plan_dict.get("recommendations", [])
            )
            
        except Exception as e:
            logger.warning(f"LLM planning failed, using fallback: {e}")
            return self._create_fallback_plan(agent_input, analysis)
    
    # Known ligand residue names (non-standard residues that need parameters)
    KNOWN_LIGAND_RESNAMES = {
        'ATP', 'ADP', 'AMP', 'GTP', 'GDP', 'GMP', 'NAD', 'NAP', 'FAD', 'FMN',
        'HEM', 'LIG', 'UNL', 'UNK', 'DRG',
    }
    
    # Standard ions / waters / common cofactors that are NOT ligands
    STANDARD_RESNAMES = {
        'HOH', 'WAT', 'SOL', 'TIP', 'MG', 'CA', 'ZN', 'MN', 'FE', 'NA', 'CL',
        'K', 'CU', 'NI', 'CO',
    }
    
    # Pre-built ligand parameter directory
    LIGAND_PARAM_DIR = Path(__file__).resolve().parent.parent.parent / "src" / "simsetup" / "amber_ligand_param"
    
    def _analyze_system(self, pdb_file: str) -> Dict[str, Any]:
        """Analyze the preprocessed system to inform setup decisions.
        
        Detects ligand residue names, ion types, and checks for pre-built
        ligand parameters in src/simsetup/amber_ligand_param/.
        """
        analysis = {
            "has_ligand": False,
            "has_ions": False,
            "estimated_atoms": 0,
            "system_type": "protein_only",
            "ligand_resnames": [],
            "ion_resnames": [],
            "ligand_params_available": {},  # {resname: path_to_itp} for pre-built params
            "ligand_params_missing": [],    # resnames that need generation
        }
        
        if os.path.exists(pdb_file):
            try:
                with open(pdb_file, 'r') as f:
                    lines = f.readlines()
                
                heteroatoms = [l for l in lines if l.startswith('HETATM')]
                analysis["estimated_atoms"] = len([l for l in lines if l.startswith(('ATOM', 'HETATM'))])
                
                # Extract unique residue names from HETATM records
                het_resnames = set()
                for l in heteroatoms:
                    parts = l.split()
                    if len(parts) > 3:
                        het_resnames.add(parts[3].strip())
                
                # Classify: ions vs ligands
                ion_names = het_resnames & self.STANDARD_RESNAMES
                # Ligands: anything in KNOWN_LIGAND_RESNAMES, or any HETATM residue
                # that is not a standard residue/ion/water and has > 5 atoms
                ligand_names = het_resnames & self.KNOWN_LIGAND_RESNAMES
                
                # Also detect unknown HETATM residues with many atoms (likely ligands)
                remaining = het_resnames - self.STANDARD_RESNAMES - ligand_names
                for resname in remaining:
                    atom_count = sum(1 for l in heteroatoms if len(l.split()) > 3 and l.split()[3].strip() == resname)
                    if atom_count > 5:
                        ligand_names.add(resname)
                
                analysis["ligand_resnames"] = sorted(ligand_names)
                analysis["ion_resnames"] = sorted(ion_names - {'HOH', 'WAT', 'SOL', 'TIP'})
                analysis["has_ligand"] = len(ligand_names) > 0
                analysis["has_ions"] = len(analysis["ion_resnames"]) > 0
                
                # Check for pre-built ligand parameters
                for resname in analysis["ligand_resnames"]:
                    itp_path = self.LIGAND_PARAM_DIR / f"{resname}.itp"
                    if itp_path.exists():
                        analysis["ligand_params_available"][resname] = str(itp_path)
                        logger.info(f"Found pre-built parameters for {resname}: {itp_path}")
                    else:
                        analysis["ligand_params_missing"].append(resname)
                        logger.info(f"No pre-built parameters for {resname} — will need generation")
                
                if analysis["has_ligand"] and analysis["has_ions"]:
                    analysis["system_type"] = "protein_ligand_ion"
                elif analysis["has_ligand"]:
                    analysis["system_type"] = "protein_ligand"
                    
            except Exception as e:
                logger.warning(f"Could not analyze system: {e}")
                
        return analysis
    
    def _build_planning_prompt(self, agent_input: SimSetupAgentInput, 
                               analysis: Dict[str, Any], state: MDState) -> str:
        """Build LLM planning prompt - use planner's detailed instructions if available"""
        
        # Check if we have detailed instructions from planner
        if agent_input.additional_instructions:
            logger.info("Using planner's detailed instructions for setup")
            return self._build_prompt_from_planner_instructions(
                agent_input, analysis, agent_input.additional_instructions, state
            )
        
        # Otherwise use standard config-based prompt
        return self._build_standard_planning_prompt(agent_input, analysis)
    
    def _build_prompt_from_planner_instructions(self, agent_input: SimSetupAgentInput,
                                                analysis: Dict[str, Any],
                                                planner_instructions: str,
                                                state: MDState) -> str:
        """Build prompt using planner's detailed natural language instructions"""
        
        # Get available tools for reference
        tool_metadata = get_tool_metadata()
        tools_list = []
        
        for tool_info in tool_metadata.values():
            tool_entry = f"→ {tool_info['name']}\n"
            tool_entry += f"  {tool_info['description']}\n"
            
            if tool_info['args']:
                tool_entry += "  Parameters:\n"
                for arg_name, arg_details in tool_info['args'].items():
                    required = "required" if arg_details['required'] else "optional"
                    desc = arg_details.get('description', 'No description')
                    tool_entry += f"    • {arg_name} ({required}): {desc}\n"
            
            tools_list.append(tool_entry)
        
        tools_list_str = "\n".join(tools_list)
        
        # Format analysis
        analysis_lines = [
            f"- System Type: {analysis.get('system_type', 'unknown')}",
            f"- Estimated Atoms: {analysis.get('estimated_atoms', 0)}",
            f"- Has Ligand: {analysis.get('has_ligand', False)}",
            f"- Ligand Residues: {analysis.get('ligand_resnames', [])}",
            f"- Has Ions: {analysis.get('has_ions', False)}",
            f"- Ion Residues: {analysis.get('ion_resnames', [])}",
        ]
        if analysis.get('ligand_params_available'):
            for resname, path in analysis['ligand_params_available'].items():
                analysis_lines.append(f"- Pre-built params for {resname}: AVAILABLE (no need to generate)")
        for resname in analysis.get('ligand_params_missing', []):
            analysis_lines.append(f"- Pre-built params for {resname}: MISSING (must use generate_ligand_parameters)")
        analysis_str = "\n".join(analysis_lines)
        
        # Extract file registry information
        file_registry = state.get("file_registry", {})
        if file_registry:
            registry_str = "\n**Files Available from Preprocessing:**\n"
            for file_path, metadata in file_registry.items():
                filename = Path(file_path).name
                file_type = metadata.get("type", "unknown")
                description = metadata.get("description", "")
                registry_str += f"- {filename} (type: {file_type}) - {description}\n"
        else:
            registry_str = "\n**Files Available from Preprocessing:** None registered\n"
        
        return f"""You are a GROMACS molecular dynamics expert executing a detailed plan from the workflow planner.

**System Information:**
- Cleaned PDB: {agent_input.cleaned_pdb}
- Force Field: {agent_input.force_field}
- Water Model: {agent_input.water_model}
- Temperature: {agent_input.temperature} K
- Pressure: {agent_input.pressure} bar

**System Analysis:**
{analysis_str}
{registry_str}

**DETAILED INSTRUCTIONS FROM PLANNER:**
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{planner_instructions}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**Available Tools:**
{tools_list_str}

**CRITICAL INSTRUCTIONS:**
- You MUST ONLY use the tools listed above - do NOT invent or suggest non-existent tools
- Every "tool_name" in your plan must match exactly one of the tool names listed above
- FORBIDDEN tool names: "none", "manual", "skip", "custom", "placeholder", or any made-up tool
- If a required capability is missing, either:
  a) Use available tools creatively to achieve the same goal, OR
  b) OMIT that step entirely from your plan (do NOT include it with tool_name="none")
- When you cannot perform a step, simply do NOT include it in the steps array

**FILE PATH REQUIREMENTS:**
- In tool_params, you MUST specify only FILENAMES, never full paths
- ❌ WRONG: "output_file": "/path/to/file.gro" or "output_file": "working_dir/simsetup/file.gro"
- ✅ CORRECT: "output_file": "file.gro"
- The system automatically handles directory management - all outputs go to working_dir/simsetup/
- Examples:
  • "topology_file": "topol.top" (not "/home/user/working_dir/simsetup/topol.top")
  • "coordinate_file": "processed.gro" (not "working_dir/simsetup/processed.gro")
  • "output_file": "solvated.gro" (not "./solvated.gro")

Your task: Create a detailed, step-by-step execution plan that follows the planner's instructions above.
The plan should specify which tools to call and in what order to achieve the planner's objectives.
ONLY include steps that use valid tools from the list above.

Output as JSON with this structure:
{{
  "reasoning": "How you'll implement the planner's instructions",
  "overview": "High-level summary",
  "steps": [
    {{
      "name": "step name",
      "description": "what it does",
      "tool_name": "tool to call",
      "tool_params": {{"param": "value"}},
      "reason": "why it's needed per planner's instructions"
    }}
  ],
  "potential_issues": ["issue1"],
  "recommendations": ["rec1"]
}}
"""
    
    def _build_standard_planning_prompt(self, agent_input: SimSetupAgentInput,
                                        analysis: Dict[str, Any]) -> str:
        """Build LLM planning prompt from config template using dynamic tool metadata"""
        config_prompt = self.config.get("llm", {}).get("planning_prompt_template", "")
        
        # Get available tools list dynamically from tool metadata
        tool_metadata = get_tool_metadata()
        tools_list = []
        
        for tool_info in tool_metadata.values():
            tool_entry = f"→ {tool_info['name']}\n"
            tool_entry += f"  {tool_info['description']}\n"
            
            if tool_info['args']:
                tool_entry += "  Parameters:\n"
                for arg_name, arg_details in tool_info['args'].items():
                    required = "required" if arg_details['required'] else "optional"
                    desc = arg_details.get('description', 'No description')
                    tool_entry += f"    • {arg_name} ({required}): {desc}\n"
            
            tools_list.append(tool_entry)
        
        tools_list_str = "\n".join(tools_list)
        
        # Format analysis for prompt
        analysis_lines = [
            f"- System Type: {analysis.get('system_type', 'unknown')}",
            f"- Estimated Atoms: {analysis.get('estimated_atoms', 0)}",
            f"- Has Ligand: {analysis.get('has_ligand', False)}",
            f"- Ligand Residues: {analysis.get('ligand_resnames', [])}",
            f"- Has Ions: {analysis.get('has_ions', False)}",
            f"- Ion Residues: {analysis.get('ion_resnames', [])}",
        ]
        if analysis.get('ligand_params_available'):
            for resname, path in analysis['ligand_params_available'].items():
                analysis_lines.append(f"- Pre-built params for {resname}: AVAILABLE (no need to generate)")
        for resname in analysis.get('ligand_params_missing', []):
            analysis_lines.append(f"- Pre-built params for {resname}: MISSING (must use generate_ligand_parameters)")
        analysis_str = "\n".join(analysis_lines)
        
        # Use template or build basic prompt
        if config_prompt:
            return config_prompt.format(
                cleaned_pdb=agent_input.cleaned_pdb,
                user_goal=agent_input.user_goal,
                force_field=agent_input.force_field,
                water_model=agent_input.water_model,
                temperature=agent_input.temperature,
                pressure=agent_input.pressure,
                analysis=analysis_str,
                tools_list=tools_list_str
            )
        else:
            # Fallback prompt
            return f"""
You are a GROMACS molecular dynamics simulation expert. Create a setup plan for:

System: {agent_input.cleaned_pdb}
Goal: {agent_input.user_goal}
Analysis: {analysis_str}

Available tools:
{tools_list_str}

**CRITICAL: You MUST ONLY use the tools listed above. Do NOT invent or suggest non-existent tools.**

Return JSON with: reasoning, overview, steps (name, description, tool_name, tool_params, reason)
"""
    
    def _extract_plan_json(self, content: str) -> Dict[str, Any]:
        """Extract and parse JSON plan from LLM response"""
        import re
        
        # Try to find JSON block in response
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass
        
        # Fallback: return minimal structure
        return {
            "reasoning": content,
            "overview": "Simulation setup plan",
            "steps": []
        }
    
    def _create_fallback_plan(self, agent_input: SimSetupAgentInput, 
                             analysis: Dict[str, Any]) -> SimSetupPlan:
        """
        Create template-based fallback plan when LLM fails
        Uses workflows from config.yaml
        """
        system_type = analysis.get("system_type", "protein_only")
        
        # Standard GROMACS workflow for all system types
        steps = [
            SimSetupStep(
                name="Build Topology",
                description=f"Generate GROMACS topology for {system_type} system using pdb2gmx",
                tool_name="build_topology",
                tool_params={
                    "pdb_file": agent_input.cleaned_pdb,
                    "force_field": agent_input.force_field,
                    "water_model": agent_input.water_model
                },
                reason="Required to create force field parameters and topology file"
            ),
            SimSetupStep(
                name="Build Simulation Box",
                description="Create cubic simulation box with 1.0 nm buffer",
                tool_name="build_simulation_box",
                tool_params={
                    "box_type": "cubic",
                    "box_distance": 1.0
                },
                reason="Define periodic boundary conditions for simulation"
            ),
            SimSetupStep(
                name="Solvate System",
                description=f"Add {agent_input.water_model} water molecules",
                tool_name="solvate_system",
                tool_params={
                    "water_model": "spc216"
                },
                reason="Simulate aqueous environment"
            ),
            SimSetupStep(
                name="Generate MDP Files",
                description="Create parameter files for all simulation phases",
                tool_name="generate_mdp_files",
                tool_params={
                    "temperature": agent_input.temperature,
                    "pressure": agent_input.pressure
                },
                reason="Define simulation protocols for minimization, equilibration, and production"
            ),
            SimSetupStep(
                name="Add Ions",
                description="Neutralize system and add 0.15 M NaCl",
                tool_name="add_ions",
                tool_params={
                    "neutral": True,
                    "concentration": 0.15
                },
                reason="Maintain electroneutrality and physiological salt concentration"
            ),
            SimSetupStep(
                name="Generate TPR File",
                description="Create binary run input file (minim.tpr) for energy minimization",
                tool_name="generate_tpr_file",
                tool_params={
                    "mdp_file": "minim.mdp"
                },
                reason="Prepare system for HPC submission - TPR file contains all simulation parameters"
            ),
        ]
        
        return SimSetupPlan(
            reasoning="Using standard GROMACS setup workflow (LLM fallback)",
            overview=f"Standard {system_type} simulation system setup",
            steps=steps,
            potential_issues=[],
            recommendations=["Verify topology parameters before production run"]
        )
    
    def _execute_plan(self, agent_input: SimSetupAgentInput, plan: SimSetupPlan,
                     state: MDState) -> SimSetupResult:
        """
        Execute setup plan step-by-step using tool executor
        Tracks file outputs and chains them between steps
        """
        execution_log = []
        issues = []
        warnings = []
        generated_files = {}
        
        current_gro = None
        topology_file = None
        mdp_files = {}
        box_dimensions = None
        water_molecules = None
        ion_count = None
        
        # Get execution limits from config
        agent_config = self.config.get("agent", {})
        max_retries = agent_config.get("max_tool_retries", 2)
        max_steps = agent_config.get("max_total_steps", 20)
        fail_fast = agent_config.get("fail_fast", False)
        
        # Get simsetup directory
        simsetup_dir = state.get("simsetup_directory", self.tool_executor.working_dir)
        
        try:
            # Enforce max steps limit
            if len(plan.steps) > max_steps:
                warnings.append(f"Plan has {len(plan.steps)} steps, limiting to {max_steps}")
                plan.steps = plan.steps[:max_steps]
            
            for i, step in enumerate(plan.steps):
                # Validate tool name - skip invalid placeholder names
                invalid_tools = ["none", "manual", "skip", "custom", "placeholder", ""]
                if not step.tool_name or step.tool_name.lower() in invalid_tools:
                    skip_msg = f"Skipping step {i+1} '{step.name}': invalid tool name '{step.tool_name}'"
                    execution_log.append(f"\n⚠ {skip_msg}")
                    warnings.append(skip_msg)
                    log_agent_action("setup", f"Step {i+1}/{len(plan.steps)} skipped", {
                        "step": step.name,
                        "reason": f"Invalid tool name: {step.tool_name}"
                    })
                    continue  # Skip this step entirely
                
                # --- Pre-built ligand parameter shortcut ---
                # If the plan asks to generate_ligand_parameters but we already
                # have a pre-built .itp, copy it into simsetup and skip the tool.
                if step.tool_name == "generate_ligand_parameters":
                    analysis = getattr(self, '_last_analysis', {})
                    available = analysis.get('ligand_params_available', {})
                    # Determine which ligand this step targets
                    step_params = step.tool_params or {}
                    # Try to match by ligand_pdb filename (e.g. "2_ligand.pdb" → look for resnames)
                    matched_resname = None
                    for resname in available:
                        if resname.lower() in step.name.lower() or resname.lower() in step.description.lower():
                            matched_resname = resname
                            break
                    # Fallback: if only one ligand and one pre-built param, use it
                    if not matched_resname and len(available) == 1:
                        matched_resname = next(iter(available))
                    
                    if matched_resname:
                        src_itp = Path(available[matched_resname])
                        dest_itp = Path(simsetup_dir) / f"{matched_resname}.itp"
                        shutil.copy2(str(src_itp), str(dest_itp))
                        # Also copy .gro if it exists alongside the .itp
                        src_gro = src_itp.with_suffix('.gro')
                        if src_gro.exists():
                            dest_gro = Path(simsetup_dir) / f"{matched_resname}.gro"
                            shutil.copy2(str(src_gro), str(dest_gro))
                        
                        msg = (f"Using pre-built parameters for {matched_resname} "
                               f"from {src_itp} (skipping acpype generation)")
                        execution_log.append(f"\n--- Step {i+1}: {step.name} ---")
                        execution_log.append(f"✓ {msg}")
                        generated_files[str(dest_itp)] = f"Ligand topology for {matched_resname} (pre-built)"
                        log_agent_action("setup", f"Step {i+1}/{len(plan.steps)} used pre-built params", {
                            "step": step.name,
                            "ligand": matched_resname,
                            "itp": str(dest_itp)
                        })
                        log_file_operation("setup", "copy", str(dest_itp), True,
                                          f"Pre-built ligand params for {matched_resname}")
                        logger.info(msg)
                        continue  # Skip to next step
                
                # Log step start
                log_agent_action("setup", f"Executing step {i+1}/{len(plan.steps)}", {
                    "step": step.name,
                    "tool": step.tool_name
                })
                
                execution_log.append(f"\n--- Step {i+1}: {step.name} ---")
                execution_log.append(f"Description: {step.description}")
                execution_log.append(f"Tool: {step.tool_name}")
                execution_log.append(f"Reason: {step.reason}")
                
                # Prepare tool parameters
                tool_params = dict(step.tool_params) if step.tool_params else {}
                
                # CRITICAL: Normalize all file paths to ensure directory isolation
                # Tools should only receive filenames, and working_dir handles the rest
                from ..utils import normalize_tool_params_for_agent
                tool_params = normalize_tool_params_for_agent(
                    tool_params,
                    simsetup_dir,
                    param_names=[
                        "pdb_file", "coordinate_file", "topology_file", "mdp_file",
                        "protein_pdb", "ligand_pdb", "ion_pdb", "ligand_itp",
                        "input_structure", "restraint_file", "output_file", "output_path"
                    ]
                )
                
                # Copy input files to simsetup directory if they exist elsewhere
                path_keys = ["pdb_file", "coordinate_file", "topology_file", "mdp_file",
                            "protein_pdb", "ligand_pdb", "ion_pdb", "ligand_itp",
                            "input_structure", "restraint_file"]
                            
                for path_key in path_keys:
                    if path_key in tool_params:
                        filename = tool_params[path_key]  # Already normalized to filename
                        if isinstance(filename, str) and filename:
                            simsetup_path = Path(simsetup_dir) / filename
                            
                            if not simsetup_path.exists():
                                # Try to find file from state or other directories
                                # Check preprocess directory
                                preprocess_dir = str(Path(state.get("working_directory", "working_dir")) / "preprocess")
                                preprocess_path = Path(preprocess_dir) / filename
                                
                                if preprocess_path.exists():
                                    shutil.copy2(str(preprocess_path), str(simsetup_path))
                                    logger.info(f"Copied {filename} from preprocess to simsetup")
                                else:
                                    # Check if absolute path was stored in state
                                    for state_key in ["cleaned_pdb", "raw_pdb", "topology", "coordinates"]:
                                        state_value = state.get(state_key)
                                        if state_value and Path(state_value).name == filename and Path(state_value).exists():
                                            shutil.copy2(state_value, str(simsetup_path))
                                            logger.info(f"Copied {filename} from {state_value} to simsetup")
                                            break
                
                # ALWAYS force output_dir and working_dir to simsetup directory
                # regardless of what the LLM plan suggests — prevents file leaks
                tool_params["output_dir"] = simsetup_dir
                tool_params["working_dir"] = simsetup_dir
                
                # Tool-specific default output filenames (relative paths)
                if step.tool_name == "build_topology" and "output_file" not in tool_params:
                    tool_params["output_file"] = "processed.gro"
                    if "topology_file" not in tool_params:
                        tool_params["topology_file"] = "topol.top"
                        
                elif step.tool_name == "build_simulation_box" and "output_file" not in tool_params:
                    tool_params["output_file"] = "boxed.gro"
                    
                elif step.tool_name == "solvate_system" and "output_file" not in tool_params:
                    tool_params["output_file"] = "solvated.gro"
                    # Set defaults if not specified
                    if "temperature" not in tool_params:
                        tool_params["temperature"] = 300.0
                    if "pressure" not in tool_params:
                        tool_params["pressure"] = 1.0
                    
                    # Execute the tool (will generate all MDP files: minim, nvt, npt, md, ions)
                    mdp_result = self.tool_executor.execute_tool("generate_mdp_files", tool_params)
                    
                    if mdp_result.get("success"):
                        # Extract generated MDP file paths
                        generated_mdp_files = mdp_result.get("mdp_files", {})
                        for phase, mdp_path in generated_mdp_files.items():
                            mdp_files[phase] = mdp_path
                            generated_files[mdp_path] = f"MDP file for {phase} phase"
                            log_file_operation("setup", "create", mdp_path, True)
                        
                        execution_log.append(f"✓ Generated {len(mdp_files)} MDP files: {list(mdp_files.keys())}")
                        log_agent_action("setup", f"MDP files generated", {
                            "count": len(mdp_files),
                            "phases": list(mdp_files.keys())
                        })
                    else:
                        error_msg = mdp_result.get("error", "Unknown error")
                        execution_log.append(f"✗ MDP generation failed: {error_msg}")
                        issues.append(f"MDP generation failed: {error_msg}")
                        log_agent_action("setup", "MDP generation failed", {"error": error_msg})
                        if fail_fast:
                            break
                    
                    continue  # Skip to next step (don't execute tool again below)
                    
                elif step.tool_name == "add_ions":
                    if current_gro:
                        tool_params["coordinate_file"] = Path(current_gro).name  # Just filename
                    if topology_file:
                        tool_params["topology_file"] = Path(topology_file).name  # Just filename
                    
                    # Use ions.mdp if available, otherwise minim.mdp (just filename)
                    if "ions" in mdp_files:
                        tool_params["mdp_file"] = Path(mdp_files["ions"]).name
                    elif "minim" in mdp_files:
                        tool_params["mdp_file"] = Path(mdp_files["minim"]).name
                    else:
                        # MDP files not generated - log error and skip
                        error_msg = "Cannot add ions: No MDP files available. Run generate_mdp_files first."
                        execution_log.append(f"✗ {error_msg}")
                        issues.append(error_msg)
                        log_agent_action("setup", "add_ions skipped", {"error": error_msg})
                        if fail_fast:
                            break
                        continue  # Skip this step
                    
                    tool_params["output_file"] = "system.gro"  # Relative to working_dir
                    tool_params["working_dir"] = simsetup_dir  # Critical for backup files
                
                elif step.tool_name == "generate_tpr_file":
                    # Set up parameters for TPR generation
                    coord_filename = None
                    if current_gro:
                        coord_filename = Path(current_gro).name  # Just filename
                        tool_params["coordinate_file"] = coord_filename
                    if topology_file:
                        tool_params["topology_file"] = Path(topology_file).name  # Just filename
                    
                    # Use minim.mdp if available, or the mdp_file specified in params
                    if "mdp_file" not in tool_params and "minim" in mdp_files:
                        tool_params["mdp_file"] = Path(mdp_files["minim"]).name
                    elif "mdp_file" in tool_params:
                        # If mdp_file is specified, ensure it's just the filename
                        tool_params["mdp_file"] = Path(tool_params["mdp_file"]).name
                    
                    # Set restraint file (typically same as coordinate file for position restraints)
                    # DEFAULT: Use the same file as coordinate_file (most common for position restraints)
                    if "restraint_file" not in tool_params:
                        if coord_filename:
                            tool_params["restraint_file"] = coord_filename
                    elif "restraint_file" in tool_params:
                        tool_params["restraint_file"] = Path(tool_params["restraint_file"]).name
                    
                    # Default output name
                    if "output_tpr" not in tool_params:
                        mdp_name = Path(tool_params.get("mdp_file", "minim.mdp")).stem
                        tool_params["output_tpr"] = f"{mdp_name}.tpr"
                    
                    tool_params["working_dir"] = simsetup_dir
                
                execution_log.append(f"Parameters: {json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in tool_params.items()}, indent=2)}")
                
                # Execute tool with retry logic
                retry_count = 0
                result = None
                
                while retry_count <= max_retries:
                    result = self.tool_executor.execute_tool(step.tool_name, tool_params)
                    
                    if result.get("success"):
                        break  # Success, exit retry loop
                    
                    retry_count += 1
                    if retry_count <= max_retries:
                        execution_log.append(f"⚠ Retry {retry_count}/{max_retries}: {result.get('error')}")
                    else:
                        execution_log.append(f"✗ Max retries ({max_retries}) exceeded")
                
                # Process results
                if result and result.get("success"):
                    execution_log.append(f"✓ Success: {result.get('message', 'Step completed')}")
                    
                    # Update current state from results (store absolute paths internally)
                    if "output_file" in result:
                        output = result["output_file"]
                        # If relative path, make absolute with simsetup_dir
                        if not Path(output).is_absolute():
                            current_gro = str(Path(simsetup_dir) / output)
                        else:
                            current_gro = output
                        generated_files[current_gro] = step.description
                        log_file_operation("setup", "create", current_gro, True)
                        
                    if "topology_file" in result:
                        topo = result["topology_file"]
                        # If relative path, make absolute with simsetup_dir
                        if not Path(topo).is_absolute():
                            topology_file = str(Path(simsetup_dir) / topo)
                        else:
                            topology_file = topo
                        generated_files[topology_file] = "GROMACS topology file"
                        log_file_operation("setup", "create", topology_file, True)
                        
                    if "box_dimensions" in result:
                        box_dimensions = result["box_dimensions"]
                        
                    if "water_molecules" in result:
                        water_molecules = result["water_molecules"]
                        
                    if "ions_added" in result:
                        ion_count = result["ions_added"]
                    
                    if "output_tpr" in result:
                        tpr = result["output_tpr"]
                        # If relative path, make absolute with simsetup_dir
                        if not Path(tpr).is_absolute():
                            tpr_path = str(Path(simsetup_dir) / tpr)
                        else:
                            tpr_path = tpr
                        generated_files[tpr_path] = "GROMACS binary run input file (TPR)"
                        log_file_operation("setup", "create", tpr_path, True)
                    
                    # Log step completion
                    log_agent_action("setup", f"Step {i+1}/{len(plan.steps)} completed", {
                        "step": step.name,
                        "tool": step.tool_name,
                        "status": "✅ SUCCESS"
                    })
                    
                    if result.get("warning"):
                        warnings.append(f"{step.name}: {result['warning']}")
                else:
                    error_msg = result.get('error', 'Failed to execute') if result else 'Tool execution failed'
                    execution_log.append(f"✗ Failed after {retry_count} attempts: {error_msg}")
                    issues.append(f"{step.name}: {error_msg}")
                    
                    log_agent_action("setup", f"Step {i+1}/{len(plan.steps)} failed", {
                        "step": step.name,
                        "tool": step.tool_name,
                        "status": "❌ FAILED",
                        "error": error_msg
                    })
                    
                    if fail_fast:
                        execution_log.append("⚠ Stopping execution (fail_fast enabled)")
                        break
            
            execution_log_str = "\n".join(execution_log)
            
            return SimSetupResult(
                success=len(issues) == 0,
                coordinates=current_gro,
                topology=topology_file,
                mdp_files=mdp_files,
                box_dimensions=box_dimensions,
                water_molecules=water_molecules,
                ion_count=ion_count,
                report=f"Setup completed: {len(plan.steps)} steps executed",
                issues=issues,
                warnings=warnings,
                generated_files=generated_files,
                execution_log=execution_log_str
            )
            
        except Exception as e:
            return SimSetupResult(
                success=False,
                report=f"Setup failed: {str(e)}",
                issues=[str(e)],
                warnings=warnings,
                generated_files=generated_files,
                execution_log="\n".join(execution_log)
            )
    
    def _update_state(self, state: MDState, agent_output: SimSetupAgentOutput):
        """Update workflow state with setup results"""
        if agent_output.supervisor_update:
            state.update(agent_output.supervisor_update)
        
        state["setup_report"] = agent_output.result.report
        state["setup_issues"] = agent_output.result.issues
        state["setup_warnings"] = agent_output.result.warnings
        state["setup_execution_log"] = agent_output.result.execution_log
        
        # Initialize file registry if not present
        if "file_registry" not in state or state["file_registry"] is None:
            state["file_registry"] = {}
        
        # Register all generated files with metadata
        for file_path, description in agent_output.result.generated_files.items():
            # Determine file type from filename
            file_type = "unknown"
            if ".top" in file_path:
                file_type = "topology"
            elif ".gro" in file_path:
                file_type = "coordinates"
            elif ".mdp" in file_path:
                file_type = "mdp"
            elif ".itp" in file_path:
                file_type = "topology_include"
            
            state["file_registry"][file_path] = {
                "type": file_type,
                "description": description,
                "stage": "simsetup"
            }
