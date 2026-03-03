"""
Prompt Enricher for Supervisor

Enriches user goals with PDB/file context using LLM rephrasing.
"""
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def rephrase_with_context(
    user_goal: str,
    context_type: str,
    context_data: Dict[str, Any],
    llm_client,
    config: Dict[str, Any]
) -> str:
    """
    Universal LLM rephrasing function that works with any context type.
    
    Args:
        user_goal: User's natural language goal
        context_type: Type of context ("pdb" or "files")
        context_data: Context information dict
            - For "pdb": {"pdb_summary": str}
            - For "files": {"file_summary": str}
        llm_client: LLM client instance
        config: Supervisor configuration
        
    Returns:
        Rephrased goal string
    """
    if not llm_client:
        return user_goal
    
    try:
        # Import here to avoid circular dependencies
        from agentic.utils import log_llm_interaction
        
        # Select appropriate prompt template based on context type
        if context_type == "pdb":
            prompt_template = config.get("input_validation", {}).get("goal_rephrase_prompt", "")
            pdb_summary = context_data.get("pdb_summary", "")
            if not prompt_template:
                return user_goal
            formatted_prompt = prompt_template.format(user_goal=user_goal, pdb_summary=pdb_summary)
            agent_name = "supervisor.goal_rephrasing"
            
        elif context_type == "files":
            prompt_template = config.get("input_validation", {}).get("analysis_rephrase_prompt", "")
            file_summary = context_data.get("file_summary", "")
            if not prompt_template:
                return user_goal
            formatted_prompt = prompt_template.format(user_goal=user_goal, file_summary=file_summary)
            agent_name = "supervisor.analysis_goal_rephrasing"
            
        else:
            logger.warning(f"Unknown context type: {context_type}, returning original goal")
            return user_goal
        
        # Send formatted prompt to LLM
        response = llm_client.prompt(
            prompt=formatted_prompt,
            temperature=0.3,
            max_tokens=300
        )
        
        # Log the interaction
        log_llm_interaction(
            agent_name=agent_name,
            prompt=formatted_prompt,
            response=response
        )
        
        return response.strip() if response.strip() and len(response.strip()) > 10 else user_goal
        
    except Exception as e:
        logger.warning(f"Failed to rephrase goal with LLM: {e}")
        return user_goal


def enrich_prompt_with_context(
    user_goal: str,
    context_type: str,
    context_data: Dict[str, Any],
    llm_client,
    config: Dict[str, Any]
) -> str:
    """
    Universal prompt enrichment function that works with any context type.
    
    Args:
        user_goal: User's natural language goal
        context_type: Type of context ("pdb" or "files")
        context_data: Context information dict
            - For "pdb": {"pdb_analysis": Dict, "pdb_summary": str}
            - For "files": {"file_info": Dict}
        llm_client: LLM client instance
        config: Supervisor configuration
        
    Returns:
        Enriched prompt string combining rephrased goal and context
    """
    from .component_parser import build_human_summary
    
    if context_type == "pdb":
        # Build PDB summary for rephrasing
        pdb_summary = context_data.get("pdb_summary", "")
        if not pdb_summary:
            pdb_analysis = context_data.get("pdb_analysis", {})
            pdb_summary = build_human_summary(pdb_analysis)
        
        # Rephrase goal with PDB context
        rephrased_goal = rephrase_with_context(
            user_goal=user_goal,
            context_type="pdb",
            context_data={"pdb_summary": pdb_summary},
            llm_client=llm_client,
            config=config
        )
        
        # Build detailed PDB information section
        pdb_analysis = context_data.get("pdb_analysis", {})
        details_parts = [f"**PDB Structure Overview:** {pdb_summary}"]
        
        if pdb_analysis.get("protein", {}).get("present"):
            chains_info = pdb_analysis.get("protein", {}).get("chains", {})
            if chains_info:
                details_parts.append(f"**Available Protein Chains:** {', '.join(chains_info.keys())}")
        
        if pdb_analysis.get("ligands", {}).get("present"):
            ligand_names = pdb_analysis.get("ligands", {}).get("residue_names", [])
            details_parts.append(f"**Ligands Present:** {', '.join(ligand_names)}")
        
        details_section = "\n".join(details_parts)
        
        # Combine rephrased goal with PDB details
        enhanced_prompt = f"{rephrased_goal}\n\n{details_section}"
        return enhanced_prompt.strip()
        
    elif context_type == "files":
        # Build file summary for rephrasing
        file_info = context_data.get("file_info", {})
        file_summary_parts = []
        if file_info.get("topology_file"):
            file_summary_parts.append(f"Topology: {file_info['topology_file']}")
        if file_info.get("trajectory_file"):
            file_summary_parts.append(f"Trajectory: {file_info['trajectory_file']}")
        if file_info.get("energy_file"):
            file_summary_parts.append(f"Energy: {file_info['energy_file']}")
        if file_info.get("hpc_output_dir"):
            file_summary_parts.append(f"HPC Output Directory: {file_info['hpc_output_dir']}")
        
        file_summary = "\n".join(file_summary_parts) if file_summary_parts else "No files specified"
        
        # Rephrase goal with file context
        rephrased_goal = rephrase_with_context(
            user_goal=user_goal,
            context_type="files",
            context_data={"file_summary": file_summary},
            llm_client=llm_client,
            config=config
        )
        
        # Combine rephrased goal with file information
        enhanced_prompt = f"{rephrased_goal}\n\n**Available Files:**\n{file_summary}"
        return enhanced_prompt.strip()
        
    else:
        logger.warning(f"Unknown context type: {context_type}, returning original goal")
        return user_goal
