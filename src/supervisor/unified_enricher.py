"""
Unified Prompt Enrichment for Supervisor

Single enrichment function that consolidates all goal rephrasing.
Runs ONCE after input validation, before planning.
"""
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


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
    
    # 3. Task type context
    task_context = f"""
**Task Type:** {subtask_type}
**Working Directory:** {working_dir}
"""
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

Provide a clear, comprehensive rephrased goal that captures the user's intent with full context."""
    
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
        # Use agent_list from state, but enforce order
        agent_list = state.get("agent_list", [])
        # Filter FULL_ORDER to only include agents in agent_list
        return [agent for agent in FULL_ORDER if agent in agent_list]
    
    else:
        # Full task - all agents in order
        return FULL_ORDER
