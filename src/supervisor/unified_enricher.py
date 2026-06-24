"""
Unified Prompt Enrichment for Supervisor

Single enrichment function that consolidates all goal rephrasing.
Runs ONCE after input validation, before planning.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Maps CLI agent names (from --subtask flag) to internal FULL_ORDER names.
# Used when building the execution order for multi_agent workflows.
_CLI_TO_INTERNAL_AGENT = {
    "preprocess": "preprocessing",
    "hpcjob": "hpc",
}


def enrich_prompt_unified(
    state: Dict[str, Any],
    llm_client,
    config: Dict[str, Any]
) -> str:
    """
    Universal prompt enrichment that runs ONCE after input validation.
    
    Consolidates all context (PDB analysis, file info, task type) into a single
    enriched prompt that is used by the planner and all agents.
    
    Args:
        state: Current workflow state with validation results
        llm_client: LLM client instance
        config: Supervisor configuration
        
    Returns:
        Enriched prompt string
    """
    from agentic.utils import log_llm_interaction
    
    user_goal = state.get("user_goal", "")
    subtask_type = state.get("subtask_type", "full_task")
    
    # Build context information
    context_parts = []
    
    # 0. Domain context (kinase domain etc. resolved from UniProt)
    domain_context = state.get("domain_context")
    structure_request = state.get("structure_request")
    if not domain_context and structure_request:
        from src.preprocess.structure_request_parser import build_domain_context_for_agents
        domain_context = build_domain_context_for_agents(structure_request)
    if domain_context:
        context_parts.append(f"\n**Domain Simulation Target:**\n{domain_context}\n")

    # 1. PDB context (if available)
    pdb_analysis = state.get("pdb_analysis")
    if pdb_analysis:
        pdb_file = state.get("raw_pdb", "Unknown")
        atoms = pdb_analysis.get("total_atoms", 0)
        residues = pdb_analysis.get("total_residues", 0)
        components = pdb_analysis.get("components_available", {})
        
        pdb_context = f"""
**PDB Structure Information:**
- File: {pdb_file}
- Total Atoms: {atoms}
- Total Residues: {residues}
- Components: Protein: {components.get('protein', False)}, Ligand: {components.get('ligand', False)}, Water: {components.get('water', False)}
"""
        context_parts.append(pdb_context)
    
    # 2. File context (for analysis/reporter tasks)
    working_dir = state.get("working_directory", ".")
    if subtask_type in ["analysis_only", "reporter_only"]:
        import os
        file_info = []
        
        if subtask_type == "analysis_only":
            # List trajectory/topology files
            hpc_dir = os.path.join(working_dir, "hpc")
            if os.path.exists(hpc_dir):
                try:
                    files = os.listdir(hpc_dir)
                    file_info.append(f"HPC Directory: {', '.join(files[:5])}")
                except:
                    pass
        
        elif subtask_type == "reporter_only":
            # List analysis output files
            analysis_dir = os.path.join(working_dir, "analysis")
            if os.path.exists(analysis_dir):
                try:
                    files = os.listdir(analysis_dir)
                    file_info.append(f"Analysis Directory: {len(files)} files")
                    summary_file = os.path.join(analysis_dir, "analysis_summary.jsonl")
                    if os.path.exists(summary_file):
                        file_info.append(f"Analysis Summary: {summary_file}")
                except:
                    pass
        
        if file_info:
            files_context = f"""
**Available Files:**
{chr(10).join(f'- {info}' for info in file_info)}
"""
            context_parts.append(files_context)
    
    # 3. System info context (from input validation - molecular composition)
    system_info = state.get("system_info")
    if system_info and system_info.get("success"):
        sys_context = f"""
**Molecular System Information:**
- {system_info.get('summary', 'No summary available')}
- Total Atoms: {system_info.get('total_atoms', 'Unknown')}
- Total Residues: {system_info.get('total_residues', 'Unknown')}"""
        # Add component details
        components = system_info.get("components", {})
        if components:
            comp_lines = []
            for comp_name, comp_data in components.items():
                if isinstance(comp_data, dict):
                    count = comp_data.get('count', comp_data.get('n_residues', comp_data.get('n_molecules', '')))
                    comp_lines.append(f"  - {comp_name}: {count}")
            if comp_lines:
                sys_context += "\n- Components:\n" + "\n".join(comp_lines)
        # Add trajectory info if available
        traj_info = system_info.get("trajectory")
        if traj_info:
            sys_context += f"""\n- Trajectory: {traj_info.get('n_frames', 'Unknown')} frames, {traj_info.get('total_time_ns', 'Unknown')} ns"""
        sys_context += "\n"
        context_parts.append(sys_context)

    # 4. Component selection context (what user wants to simulate)
    component_selection = state.get("component_selection")
    if component_selection:
        sel_parts = []
        for comp_name in ["protein", "ligand", "ions", "water"]:
            val = component_selection.get(comp_name)
            if val is True:
                sel_parts.append(f"{comp_name}: INCLUDE")
            elif val is False:
                sel_parts.append(f"{comp_name}: EXCLUDE")
        if sel_parts:
            comp_context = f"""
**User's Component Selection:**
{chr(10).join(f'- {p}' for p in sel_parts)}
Note: Only included components should be extracted during preprocessing and set up during simulation setup.
"""
            context_parts.append(comp_context)
    
    # 5. Task type and workflow agents context
    agent_list = state.get("agent_list") or []
    execution_order = get_agent_execution_order(subtask_type, state)
    post_sim_analysis = subtask_type in ("analysis_only", "reporter_only", "multi_agent") and (
        set(agent_list or []) <= {"analysis", "reporter"}
        or execution_order == ["analysis", "reporter"]
    )

    agent_lines = []
    if execution_order:
        agent_lines.append(
            "Involved field agents (ONLY these stages — do not mention others): "
            + " → ".join(execution_order)
        )
    elif agent_list:
        agent_lines.append(
            "Involved field agents (ONLY these stages): " + ", ".join(agent_list)
        )
    if post_sim_analysis:
        agent_lines.append(
            "Trajectories already exist. Do NOT mention preprocessing, simulation setup, "
            "HPC submission, equilibration, production runs, or solvation unless the user "
            "explicitly requests those stages."
        )

    task_context = f"""
**Task Type:** {subtask_type}
**Working Directory:** {working_dir}
"""
    if agent_lines:
        task_context += "**Workflow Scope:**\n" + "\n".join(f"- {line}" for line in agent_lines) + "\n"
    context_parts.append(task_context)
    
    # Build the enrichment prompt
    if not llm_client or not llm_client.available:
        # No LLM - return goal with simple context
        if context_parts:
            return f"{user_goal}\n\n{''.join(context_parts)}"
        return user_goal
    
    # Get prompt template from config
    prompt_template = config.get("input_validation", {}).get("unified_enrichment_prompt", "")
    
    if not prompt_template:
        # Default prompt if not in config
        prompt_template = """You are helping to clarify and enrich a user's goal for MD simulation workflow.

**User's Original Goal:**
{user_goal}

{context}

**Your Task:**
Rephrase the user's goal to be more specific, structured, and actionable for the MD workflow agents.
Include:
1. What needs to be done (preprocessing, setup, simulation, analysis, reporting)
2. Which components/residues to focus on
3. What specific outputs or results are expected
4. Any constraints or special requirements

**Critical Guidelines:**
- Preserve the user's exact intent - don't add or remove steps
- If user says "preprocess and setup", that means ONLY those two steps - do NOT add simulation execution, equilibration, production runs, or trajectory generation
- "simulation setup" means preparing the input files (topology, coordinates, MDP, TPR) - NOT running the simulation
- If user specifies components (protein, ligand, ions), preserve exactly as stated
- If user excludes something (no HPC, no simulation), make that explicit
- Be concise (3-6 sentences maximum)

**Default Simulation Conditions (DO NOT CHANGE unless user explicitly requests otherwise):**
- Force field: amber99sb-ildn (do NOT switch to CHARMM or other force fields)
- Water model: tip3p (the system MUST be solvated in water, NOT vacuum)
- Temperature: 310 K, Pressure: 1 bar, NaCl: 0.15 M (physiological ionization)
"Protein only" means only the protein component from the PDB — it does NOT mean vacuum or unsolvated.
ALL simulation systems are solvated with water and ions by default. Only build vacuum/gas-phase systems if the user explicitly says "in vacuum" or "gas phase".
Only change these conditions if the user explicitly requests different values.

Provide a clear, comprehensive rephrased goal that captures the user's intent with full context.
No additional commentary or suggestions."""
    
    # Format the prompt
    formatted_prompt = prompt_template.format(
        user_goal=user_goal,
        context=''.join(context_parts)
    )
    
    try:
        # Call LLM
        response = llm_client.prompt(
            prompt=formatted_prompt,
            temperature=0.3,
            max_tokens=500
        )
        
        # Log the interaction
        log_llm_interaction(
            agent_name="supervisor.unified_enrichment",
            prompt=formatted_prompt,
            response=response
        )
        
        enriched = response.strip()
        
        # Validate response
        if len(enriched) < 20:
            logger.warning("LLM enrichment too short, using original goal")
            enriched = user_goal
        
        logger.info(f"ENRICHMENT: Created unified enriched prompt ({len(enriched)} chars)")
        return enriched
        
    except Exception as e:
        logger.error(f"ENRICHMENT: LLM enrichment failed: {e}, using original goal")
        return user_goal


def get_agent_execution_order(subtask_type: str, state: Dict[str, Any]) -> list:
    """
    Get the strict execution order for field agents.
    
    Order is ALWAYS: preprocessing → simsetup → hpc → analysis → reporter
    Agents are skipped based on what's already completed or not needed.
    
    Args:
        subtask_type: Type of task being executed
        state: Current workflow state
        
    Returns:
        List of agent names in execution order
    """
    # Define strict order
    FULL_ORDER = ["preprocessing", "simsetup", "hpc", "analysis", "reporter"]
    
    # Determine which agents to include based on task type
    if subtask_type == "reporter_only":
        return ["reporter"]
    
    elif subtask_type == "analysis_only":
        return ["analysis", "reporter"]
    
    elif subtask_type == "setup_only":
        return ["preprocessing", "simsetup"]
    
    elif subtask_type == "preprocess_only":
        return ["preprocessing"]
    
    elif subtask_type == "multi_agent":
        # Use agent_list from state, but enforce order.
        # Normalize CLI names ("preprocess" → "preprocessing", "hpcjob" → "hpc")
        # so they match the internal FULL_ORDER names.
        agent_list = state.get("agent_list", [])
        normalized = [_CLI_TO_INTERNAL_AGENT.get(a, a) for a in agent_list]
        return [agent for agent in FULL_ORDER if agent in normalized]
    
    else:
        # Full task - all agents in order
        return FULL_ORDER
