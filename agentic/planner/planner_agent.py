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
        
        # All plans are now natural language format
        agent_sequence = plan.get("agent_sequence", [])
        num_agents = len(agent_sequence)
        logger.info(f"PLANNER: Created natural language plan with {num_agents} agents: {agent_sequence}")
        
        # Log detailed plan to conversation log
        from ..utils import log_agent_action
        
        # Log natural language plan details
        plan_preview = plan.get("full_plan", "")[:500]  # First 500 chars for preview
        plan_details = {
            "format": "natural_language",
            "title": plan.get("title", "N/A"),
            "agent_sequence": agent_sequence,
            "total_agents": num_agents,
            "plan_preview": plan_preview + ("..." if len(plan.get("full_plan", "")) > 500 else ""),
            "method": plan.get("method", "llm_generated")
        }
        
        log_agent_action(
            agent_name="planner",
            action="Generated Natural Language Execution Plan",
            details=plan_details
        )
        
        # Log routing
        log_supervisor_routing(
            state, 
            "supervisor",
            f"Planner: Created natural language plan with {num_agents} agents. Returning to supervisor."
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
        
        CRITICAL: Respects subtask-specific workflows (analysis-only, setup-only, etc.)
        Uses dynamic tools knowledge and domain knowledge to create comprehensive plans.
        """
        logger.info("PLANNER: Creating plan with dynamic tools and knowledge")
        
        # NEW: Detect subtask type for smarter planning
        subtask_type = state.get("subtask_type")
        if subtask_type:
            logger.info(f"PLANNER: Planning for subtask type: {subtask_type}")
        
        # Get available tools context - agent-specific for subtask workflows
        if subtask_type == "analysis_only":
            logger.info("PLANNER: Getting analysis agent tools for analysis-only workflow")
            tools_context = self._get_tools_context(agent_name="analysis")
        elif subtask_type == "setup_only":
            logger.info("PLANNER: Getting setup agent tools for setup-only workflow")
            tools_context = self._get_tools_context(agent_name="simsetup")
        elif subtask_type == "preprocess_only":
            logger.info("PLANNER: Getting preprocessing agent tools for preprocess-only workflow")
            tools_context = self._get_tools_context(agent_name="preprocess")
        else:
            # Full workflow - get all tools
            tools_context = self._get_tools_context()
        
        # Get relevant knowledge (protocols and force fields)
        knowledge_context = self._get_knowledge_context(max_chars=6000)
        
        # Build LLM prompt with all context - INCLUDE subtask type info
        planning_prompt = self._build_planning_prompt(
            structured_prompt,
            pdb_path,
            pdb_analysis,
            component_selection,
            state,
            tools_context,
            knowledge_context,
            subtask_type=subtask_type  # Pass subtask type to prompt
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
            
            # If LLM response was not a valid plan (e.g., asking questions), use fallback
            if plan is None:
                logger.warning("PLANNER: LLM response not suitable - using fallback plan")
                plan = self._create_fallback_plan(
                    structured_prompt, pdb_path, pdb_analysis, component_selection, state
                )
            
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
        knowledge_context: str,
        subtask_type: Optional[str] = None
    ) -> str:
        """Build planning prompt for execution plan creation."""
        
        # Common natural language format instructions for ALL plan types
        nl_format_instructions = """**OUTPUT FORMAT - MANDATORY:**

You MUST provide your execution plan in NATURAL LANGUAGE format ONLY.

✓ DO:
- Write a detailed prose description of the execution plan
- Organize into clear sections (Goal, Analysis, Execution Sequence, Expected Outcomes)
- Explain which agents to use and why (use agent names explicitly!)
- Describe what each agent should do in detail
- Reference specific tools agents should consider using
- Write in complete sentences and paragraphs
- Be comprehensive and explanatory

✗ DO NOT:
- Use JSON format (CRITICAL: No curly braces {}, no key-value pairs)
- Use YAML format
- Use structured data formats
- Create step-by-step numbered lists without context
- Write bullet points without explanation
- Use schemas or templates
- Output command sequences or file contents directly

Write your plan as if explaining the workflow to another expert in molecular dynamics.
Be thorough, clear, and provide reasoning for your decisions.

CRITICAL: If you output JSON, YAML, or any structured format, the plan will be rejected and the workflow will fail."""
        
        if subtask_type == "analysis_only":
            working_dir = state.get("working_directory", ".")
            return f"""Create a detailed natural language execution plan for trajectory analysis.

USER GOAL:
{structured_prompt}

TASK: Analysis-only - perform trajectory analysis on existing simulation data.
DO NOT include preprocessing, setup, or HPC agents.
ONLY create execution plan for Analysis Agent.

File Structure:
- Working Directory: {working_dir}
- Trajectory/Topology Location: {working_dir}/hpc/ (auto-discovery)
- Analysis Output Directory: {working_dir}/analysis/

**Available Analysis Agent Tools:**
{tools_context}

**CRITICAL INSTRUCTIONS:**
- Use the analysis agent's Python tools listed above (calculate_rmsd, calculate_rmsf, etc.)
- Do NOT use bash/shell commands or GROMACS CLI tools (gmx rmsf, etc.)
- The analysis agent will handle file discovery and tool execution
- Specify WHICH tools to use and what analysis to perform
- Let the analysis agent handle the implementation details

{nl_format_instructions}

Provide a comprehensive natural language plan explaining how the Analysis Agent should conduct the trajectory analysis."""

        elif subtask_type == "setup_only":
            return f"""Create a detailed natural language execution plan for MD simulation setup.

USER GOAL:
{structured_prompt}

TASK: Setup-only - generate topology and coordinate files for simulation.
Only include Setup Agent. Do NOT include preprocessing (unless explicitly requested), HPC, or analysis.

PDB File: {pdb_path or 'Not specified'}
Force Field: {state.get('force_field', 'amber99sb-ildn')}
Water Model: {state.get('water_model', 'tip3p')}

**Available Setup Agent Tools:**
{tools_context}

**CRITICAL INSTRUCTIONS:**
- Use the setup agent's tools listed above (generate_topology, create_solvation_box, etc.)
- Specify which setup tools to use and their parameters
- Focus on topology generation and system preparation

{nl_format_instructions}

Provide a comprehensive natural language plan explaining how the Setup Agent should prepare the simulation system."""

        elif subtask_type == "preprocess_only":
            return f"""Create a detailed natural language execution plan for structure preprocessing.

USER GOAL:
{structured_prompt}

TASK: Preprocessing-only - clean and validate protein structure.
Only include Preprocessing Agent. Do NOT include setup, HPC, or analysis.

PDB File: {pdb_path or 'Not specified'}

**Available Preprocessing Agent Tools:**
{tools_context}

**CRITICAL INSTRUCTIONS:**
- Use the preprocessing agent's tools listed above (remove_waters, fix_residues, add_hydrogens, etc.)
- Specify which preprocessing tools to use
- Focus on structure cleanup and validation

{nl_format_instructions}

Provide a comprehensive natural language plan explaining how the Preprocessing Agent should clean and prepare the structure."""

        else:
            components = pdb_analysis.get("components_available", {})
            return f"""Create a detailed natural language execution plan for the complete MD workflow.

USER GOAL:
{structured_prompt}

PDB File: {pdb_path}
Atoms: {pdb_analysis.get('total_atoms', '?')} | Residues: {pdb_analysis.get('total_residues', '?')}
Components: Protein={components.get('protein', False)} Ligand={components.get('ligand', False)} Water={components.get('water', False)}

Force Field: {state.get('force_field', 'amber99sb-ildn')}
Water Model: {state.get('water_model', 'tip3p')}

**Available Agents and Their Tools:**
{tools_context}

**CRITICAL INSTRUCTIONS FOR AGENT NAMING:**
You MUST explicitly name each agent involved in your plan using these EXACT phrases:
- "Preprocessing Agent" or "preprocessing agent" - for structure cleaning
- "Simulation Setup Agent" or "setup agent" - for topology and system building
- "HPC Agent" or "hpc agent" - for job submission
- "Analysis Agent" or "analysis agent" - for trajectory analysis

Write complete sentences like:
"The Preprocessing Agent will first clean the PDB structure by..."
"Next, the Simulation Setup Agent generates topology files using..."
"The HPC Agent then submits the simulation job with..."

{nl_format_instructions}

**EXAMPLE STRUCTURE:**

Goal: [Summarize what needs to be accomplished]

Workflow Execution:

The Preprocessing Agent will handle structure preparation. It will use the separate_complex_components tool to extract the protein chain, removing the ATP ligand and MG ions as requested. The add_hydrogens tool will then ensure complete protonation using the reduce method at neutral pH.

The Simulation Setup Agent will prepare the simulation system. Using build_topology, it generates AMBER99SB-ILDN topology files. The system will be placed in a cubic simulation box with adequate spacing, solvated with TIP3P water molecules, and neutralized with appropriate ions. The generate_mdp_files tool will create parameter files for a 10 ns production run.

The HPC Agent will handle job submission to the compute cluster. It will use create_slurm_script to generate an appropriate job submission script, then submit_job to initiate the simulation on the HPC system.

Expected Outcomes: [Describe final deliverables]

Provide a comprehensive natural language plan following this structure. DO NOT output JSON, YAML, or any structured data format."""
    
    def _parse_llm_plan_response(self, response: str, state: MDState) -> Optional[Dict[str, Any]]:
        """Parse LLM response. Return None if response is just asking questions."""
        import re
        
        logger.info("PLANNER: Processing LLM response")
        
        if not response:
            logger.warning("PLANNER: Empty LLM response - triggering fallback")
            return None
        
        # Detect if LLM is asking for clarification instead of providing a plan
        question_indicators = [
            r'what.*goal\s*\?',
            r'i\s+(need|require)\s+.*information',
            r'can\s+you\s+(clarify|specify)',
            r'do\s+you\s+want',
            r'are\s+there\s+any',
        ]
        
        response_lower = response.lower()
        question_count = sum(1 for pattern in question_indicators if re.search(pattern, response_lower))
        question_mark_count = response.count('?')
        
        if question_count >= 2 or question_mark_count >= 3:
            logger.warning("PLANNER: LLM response is asking questions instead of creating plan - triggering fallback")
            return None  # Signal to use fallback
        
        # CRITICAL: For subtask-specific workflows, automatically infer agent from subtask type
        # This ensures the correct agent is included even if not explicitly mentioned in prose
        subtask_type = state.get("subtask_type")
        
        if subtask_type == "analysis_only":
            # Analysis-only workflow - only analysis agent
            agent_mentions = {"analysis_agent": True}
        elif subtask_type == "setup_only":
            # Setup-only workflow - only setup agent
            agent_mentions = {"setup_agent": True}
        elif subtask_type == "preprocess_only":
            # Preprocess-only workflow - only preprocessing agent
            agent_mentions = {"preprocessing_agent": True}
        else:
            # Full workflow - extract which agents are mentioned in the plan
            agent_mentions = {
                "preprocessing_agent": bool(re.search(r'(?i)preprocessing\s+agent', response)),
                "setup_agent": bool(re.search(r'(?i)(setup|simsetup|simulation\s+setup)\s+agent', response)),
                "hpc_agent": bool(re.search(r'(?i)hpc\s+agent', response)),
                "analysis_agent": bool(re.search(r'(?i)analysis\s+agent', response))
            }
            
            # FALLBACK: If LLM didn't mention agents (e.g., returned JSON), infer from user goal
            num_agents_mentioned = sum(agent_mentions.values())
            if num_agents_mentioned == 0:
                logger.warning("PLANNER: LLM response doesn't mention any agents. Inferring from user goal.")
                user_goal = state.get("user_goal", "").lower()
                structured_prompt = state.get("structured_prompt", "").lower()
                goal_text = user_goal + " " + structured_prompt
                
                # Infer which agents are needed based on keywords in goal
                needs_preprocess = bool(re.search(r'(preprocess|clean|extract|protein)', goal_text))
                needs_setup = bool(re.search(r'(setup|simulation|topology|system|solvate|box)', goal_text))
                needs_hpc = bool(re.search(r'(hpc|submit|run|execute|cluster)', goal_text))
                needs_analysis = bool(re.search(r'analysis|analyze|rmsd|rmsf', goal_text))
                
                # Default to full workflow if can't determine
                if not any([needs_preprocess, needs_setup, needs_hpc, needs_analysis]):
                    logger.info("PLANNER: Cannot determine workflow from goal, defaulting to full workflow")
                    needs_preprocess = needs_setup = needs_hpc = True
                    needs_analysis = False  # Only if explicitly requested
                
                agent_mentions = {
                    "preprocessing_agent": needs_preprocess,
                    "setup_agent": needs_setup,
                    "hpc_agent": needs_hpc,
                    "analysis_agent": needs_analysis
                }
                
                logger.info(f"PLANNER: Inferred agents from goal: {[k for k, v in agent_mentions.items() if v]}")
        
        # Build lightweight plan structure for routing
        steps = []
        step_num = 1
        
        for agent_name, is_mentioned in agent_mentions.items():
            if is_mentioned:
                steps.append({
                    "step_number": step_num,
                    "agent": agent_name,
                    "type": "natural_language",
                    "dependencies": [step_num - 1] if step_num > 1 else []
                })
                step_num += 1
        
        plan = {
            "title": "Detailed Natural Language Execution Plan",
            "format": "natural_language",
            "full_plan": response,
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
        
        CRITICAL: Always generates NATURAL LANGUAGE plans, never structured JSON.
        Respects subtask_type to focus only on requested workflow stages.
        """
        logger.info("PLANNER: Creating fallback natural language plan from PDB analysis")
        
        subtask_type = state.get("subtask_type")
        summary = pdb_analysis.get("summary", {})
        working_dir = state.get("working_directory", ".")
        
        # Build natural language plan prose
        plan_sections = []
        agents_involved = []
        
        # Section 1: Goal Understanding
        plan_sections.append(f"**GOAL INTERPRETATION:**\n\n{structured_prompt}\n")
        
        # Section 2: PDB Analysis Summary (if not analysis-only)
        if subtask_type != "analysis_only":
            pdb_info = []
            pdb_info.append(f"PDB File: {pdb_path}")
            pdb_info.append(f"Total Atoms: {pdb_analysis.get('total_atoms', 'Unknown')}")
            if pdb_analysis.get('protein', {}).get('present'):
                pdb_info.append(f"Protein: Present ({pdb_analysis.get('total_residues', '?')} residues)")
            if pdb_analysis.get('ligands', {}).get('present'):
                ligands = pdb_analysis.get('ligands', {}).get('residue_names', [])
                pdb_info.append(f"Ligands: {', '.join(ligands)}")
            if pdb_analysis.get('water', {}).get('present'):
                pdb_info.append(f"Water: Present ({pdb_analysis.get('water', {}).get('molecule_count', '?')} molecules)")
            
            plan_sections.append(f"**PDB STRUCTURE ANALYSIS:**\n\n" + "\n".join(pdb_info) + "\n")
        
        # Section 3: Execution Sequence (detailed prose for each agent)
        execution_prose = []
        
        # === ANALYSIS-ONLY WORKFLOW ===
        if subtask_type == "analysis_only":
            agents_involved.append("analysis_agent")
            execution_prose.append(
                f"**Analysis Agent Responsibilities:**\n\n"
                f"The Analysis Agent will perform trajectory analysis on existing simulation data located "
                f"in {working_dir}/hpc/. The agent will auto-discover topology and trajectory files "
                f"(looking for .gro, .pdb, .tpr for topology and .xtc, .trr for trajectories).\n\n"
                f"Analysis tasks to perform:\n"
                f"- Calculate structural metrics (RMSD, RMSF) as requested\n"
                f"- Generate energy profiles if energy files (.edr) are available\n"
                f"- Create visualization plots for all analyses\n"
                f"- Save all results to {working_dir}/analysis/\n\n"
                f"The agent will use Python-based analysis tools (MDAnalysis, matplotlib) rather than "
                f"command-line GROMACS tools for better integration and flexibility."
            )
        
        # === FULL OR PARTIAL WORKFLOWS ===
        else:
            # Preprocessing
            if subtask_type != "setup_only":
                preprocessing_needed = []
                if summary.get("needs_hydrogen_addition"):
                    preprocessing_needed.append("adding missing hydrogens with correct protonation states")
                if pdb_analysis.get("water", {}).get("present"):
                    preprocessing_needed.append("removing water molecules")
                if component_selection.get("ligand") is False and pdb_analysis.get("ligands", {}).get("present"):
                    preprocessing_needed.append("removing ligand molecules")
                
                if preprocessing_needed or not state.get("cleaned_pdb"):
                    agents_involved.append("preprocessing_agent")
                    tasks_str = ", ".join(preprocessing_needed) if preprocessing_needed else "structure validation"
                    execution_prose.append(
                        f"**Preprocessing Agent Responsibilities:**\n\n"
                        f"The Preprocessing Agent will clean and prepare the PDB structure by {tasks_str}. "
                        f"This agent focuses solely on structure preparation and does NOT handle topology "
                        f"generation or force field assignment (those are handled by the Setup Agent).\n\n"
                        f"Tools to use: reduce (hydrogens), pdbfixer (missing atoms/residues), "
                        f"Bio.PDB (structure manipulation)\n\n"
                        f"Expected output: cleaned_pdb file ready for topology generation"
                    )
            
            # Setup
            if subtask_type not in ["analysis_only", "preprocess_only"]:
                agents_involved.append("setup_agent")
                ff = state.get('force_field', 'amber99sb-ildn')
                wm = state.get('water_model', 'tip3p')
                execution_prose.append(
                    f"\n\n**Setup Agent Responsibilities:**\n\n"
                    f"The Setup Agent will generate the complete simulation system using {ff} "
                    f"force field and {wm} water model. This includes:\n\n"
                    f"1. Topology generation (gmx pdb2gmx) for protein components\n"
                    f"2. Ligand parameterization using acpype or CGenFF if ligands are present and requested\n"
                    f"3. Defining the simulation box (gmx editconf)\n"
                    f"4. System solvation (gmx solvate)\n"
                    f"5. Adding neutralizing ions (gmx genion)\n"
                    f"6. Generating MDP parameter files for energy minimization, equilibration, and production runs\n\n"
                    f"Expected outputs: topology files (.top, .itp), coordinate files (.gro), "
                    f"and parameter files (.mdp)"
                )
            
            # HPC
            if subtask_type not in ["analysis_only", "setup_only", "preprocess_only"]:
                goal_lower = structured_prompt.lower() + state.get("user_goal", "").lower()
                hpc_excluded = any(phrase in goal_lower for phrase in [
                    "no hpc", "skip hpc", "do not submit", "don't submit", "setup only", "without hpc"
                ])
                
                if ("run" in goal_lower or "execute" in goal_lower or "simulate" in goal_lower) and not hpc_excluded:
                    agents_involved.append("hpc_agent")
                    execution_prose.append(
                        f"\n\n**HPC Agent Responsibilities:**\n\n"
                        f"The HPC Agent will submit the simulation to a compute cluster using SLURM job scheduler. "
                        f"The agent will:\n\n"
                        f"1. Generate appropriate SLURM job scripts with resource requests\n"
                        f"2. Submit energy minimization, NVT equilibration, NPT equilibration, and production MD jobs\n"
                        f"3. Monitor job status and handle failures\n"
                        f"4. Retrieve trajectory and output files upon completion\n\n"
                        f"Expected outputs: job_id, trajectory files (.xtc), energy files (.edr), coordinate files (.gro)"
                    )
                elif hpc_excluded:
                    execution_prose.append(
                        f"\n\n**HPC Submission: SKIPPED**\n\n"
                        f"User explicitly requested to skip HPC job submission. Simulation files will be "
                        f"prepared but not executed."
                    )
            
            # Analysis (for full workflows)
            if subtask_type not in ["preprocess_only", "setup_only"]:
                goal_lower = structured_prompt.lower()
                if "analyz" in goal_lower or "rmsd" in goal_lower or "rmsf" in goal_lower:
                    agents_involved.append("analysis_agent")
                    execution_prose.append(
                        f"\n\n**Analysis Agent Responsibilities:**\n\n"
                        f"After simulation completion, the Analysis Agent will perform trajectory analysis "
                        f"including RMSD (structural deviation), RMSF (per-residue flexibility), and other "
                        f"requested analyses. Results will be saved to {working_dir}/analysis/ with both "
                        f"data files and visualization plots."
                    )
        
        # Combine sections
        plan_sections.append("**EXECUTION SEQUENCE:**\n\n" + "\n".join(execution_prose))
        
        # Section 4: Expected Outcomes
        outcomes = []
        if "preprocessing_agent" in agents_involved:
            outcomes.append("- Cleaned PDB structure ready for topology generation")
        if "setup_agent" in agents_involved:
            outcomes.append("- Complete simulation system (topology, coordinates, parameters)")
        if "hpc_agent" in agents_involved:
            outcomes.append("- Completed simulation trajectory and energy data")
        if "analysis_agent" in agents_involved:
            outcomes.append("- Analysis results with plots and data files")
        
        if outcomes:
            plan_sections.append(f"\n\n**EXPECTED OUTCOMES:**\n\n" + "\n".join(outcomes))
        
        # Build complete natural language plan
        full_plan_text = "\n".join(plan_sections)
        
        # Create minimal step structure for routing (supervisor needs to know agent sequence)
        steps = []
        for i, agent_name in enumerate(agents_involved, 1):
            steps.append({
                "step_number": i,
                "agent": agent_name,
                "type": "natural_language",
                "dependencies": [i - 1] if i > 1 else []
            })
        
        plan = {
            "title": f"Fallback Natural Language Execution Plan: {subtask_type or 'full_pipeline'}",
            "format": "natural_language",
            "full_plan": full_plan_text,
            "agent_sequence": agents_involved,
            "steps": steps,
            "method": "fallback",
            "subtask_type": subtask_type
        }
        
        logger.info(f"PLANNER: Fallback natural language plan complete with {len(agents_involved)} agents: {agents_involved}")
        return plan
    
    def _create_plan_from_templates(
        self, 
        user_goal: str, 
        validated_pdb: str,
        state: MDState
    ) -> Dict[str, Any]:
        """
        DEPRECATED: Create plan using keyword-based templates.
        
        This method is no longer used as all plans are now generated in natural language format.
        Kept for reference only. Use _create_fallback_plan() instead which generates NL plans.
        """
        logger.warning("PLANNER: _create_plan_from_templates is deprecated. Use _create_fallback_plan instead.")
        
        # Redirect to fallback plan which generates natural language
        return self._create_fallback_plan(
            structured_prompt=user_goal,
            pdb_path=validated_pdb,
            pdb_analysis=state.get("pdb_analysis", {}),
            component_selection=state.get("component_selection", {}),
            state=state
        )
