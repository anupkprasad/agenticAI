"""
Supervisor Helper Tools

Utility functions for input validation, component parsing, and prompt enrichment.
"""

import logging
import re
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def parse_component_selection(user_goal: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Parse user intent to determine components for simulation."""
    goal_lower = user_goal.lower()
    explicit = {component: None for component in ["protein", "ligand", "water", "ions", "specific_chains"]}
    
    # Check explicit "only" requests
    if any(p in goal_lower for p in ["only protein", "just protein", "protein only", "extract protein"]):
        explicit.update({"protein": True, "ligand": False, "ions": False, "water": False})
    elif any(p in goal_lower for p in ["only ligand", "just ligand", "ligand only", "extract ligand"]):
        explicit.update({"protein": False, "ligand": True, "ions": False, "water": False})
    elif "complex" in goal_lower or "protein and ligand" in goal_lower:
        explicit.update({"protein": True, "ligand": True})
    
    # Check inclusions
    if any(p in goal_lower for p in ["with ligand", "include ligand", "retaining ligand", "retain ligand", "keeping ligand", "keep ligand"]):
        explicit["ligand"] = True
    if any(p in goal_lower for p in ["with water", "include water", "keep water", "retaining water", "retain water"]):
        explicit["water"] = True
    if any(p in goal_lower for p in ["with ions", "include ions", "retaining ions", "retain ions", "keeping ions", "keep ions"]):
        explicit["ions"] = True
    
    # Check exclusions
    if any(p in goal_lower for p in ["without ligand", "remove ligand", "no ligand"]):
        explicit["ligand"] = False
    if any(p in goal_lower for p in ["without water", "remove water", "no water"]):
        explicit["water"] = False
    if any(p in goal_lower for p in ["without ions", "remove ions", "no ions"]):
        explicit["ions"] = False
    
    # Check specific chains
    chain_match = re.search(r"chain\s+([A-Z](?:\s+and\s+[A-Z]|,\s*[A-Z])*)", user_goal, re.IGNORECASE)
    if chain_match:
        chains = re.findall(r"[A-Z]", chain_match.group(1).upper())
        explicit["specific_chains"] = chains
    
    # Build final selection with fallback to PDB analysis
    return {
        "protein": explicit["protein"] if explicit["protein"] is not None else analysis.get("protein", {}).get("present", False),
        "ligand": explicit["ligand"] if explicit["ligand"] is not None else analysis.get("ligands", {}).get("present", False),
        "water": explicit["water"] if explicit["water"] is not None else False,
        "ions": explicit["ions"] if explicit["ions"] is not None else analysis.get("ions", {}).get("present", False),
        "specific_chains": explicit["specific_chains"]
    }


def validate_feasibility(
    user_goal: str, 
    analysis: Dict[str, Any], 
    component_selection: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Validate if user's request is feasible given PDB contents.
    
    Args:
        user_goal: User's natural language goal
        analysis: PDB analysis results
        component_selection: Parsed component selection
        
    Returns:
        Dict with is_feasible, errors, warnings
    """
    errors = []
    warnings = []
    
    # Check if requested components exist
    if component_selection.get("protein") and not analysis.get("protein", {}).get("present"):
        errors.append("User requested protein simulation but PDB contains no protein")
    
    if component_selection.get("ligand") and not analysis.get("ligands", {}).get("present"):
        errors.append("User requested ligand simulation but PDB contains no ligand")
    
    # Check for specific chains
    if component_selection.get("specific_chains"):
        requested_chains = set(component_selection["specific_chains"])
        available_chains = set(analysis.get("chain_ids", []))
        missing_chains = requested_chains - available_chains
        
        if missing_chains:
            errors.append(
                f"Requested chains {missing_chains} not found in PDB. "
                f"Available chains: {available_chains}"
            )
    
    # Warnings for preprocessing needs
    components = analysis.get("components_available", {})
    if not components.get("hydrogens", True):
        warnings.append("PDB is missing hydrogens - will be added during preprocessing")
    
    if analysis.get("water", {}).get("present"):
        warnings.append("PDB contains water molecules - will be removed during preprocessing")
    
    return {
        "is_feasible": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


def enrich_user_prompt(
    user_goal: str,
    analysis: Dict[str, Any],
    llm_client,
    config: Dict[str, Any]
) -> str:
    """
    Enrich user's natural language prompt with validated PDB information.
    
    Uses LLM to rephrase the user's goal clearly, then adds PDB structure details.
    
    Args:
        user_goal: User's natural language goal
        analysis: PDB analysis results
        llm_client: LLM client for rephrasing
        config: Supervisor configuration
        
    Returns:
        Enriched prompt string
    """
    # Get human-readable summary from PDB analyzer
    human_summary = analysis.get("human_readable_summary", "")
    
    # If no human summary available, build a basic one
    if not human_summary:
        summary_parts = []
        if analysis.get("protein", {}).get("present"):
            residue_count = analysis.get("protein", {}).get("total_residues", 0)
            summary_parts.append(f"Protein ({residue_count} residues)")
        if analysis.get("ligands", {}).get("present"):
            ligand_names = analysis.get("ligands", {}).get("residue_names", [])
            summary_parts.append(f"Ligands: {', '.join(ligand_names)}")
        if analysis.get("water", {}).get("present"):
            water_count = analysis.get("water", {}).get("molecule_count", 0)
            summary_parts.append(f"Water ({water_count} molecules)")
        if analysis.get("ions", {}).get("present"):
            ion_types = analysis.get("ions", {}).get("types", {})
            if ion_types:
                summary_parts.append(f"Ions: {', '.join(ion_types.keys())}")
        human_summary = " | ".join(summary_parts) if summary_parts else "Unknown structure"
    
    # Use LLM to rephrase the user's goal with PDB context
    rephrased_goal = rephrase_user_goal_with_llm(user_goal, human_summary, llm_client, config)
    
    # Create enhanced prompt: rephrased goal + PDB structure
    enhanced_prompt = f"{rephrased_goal}\n\n**PDB Structure:** {human_summary}"
    
    return enhanced_prompt.strip()


def rephrase_user_goal_with_llm(
    user_goal: str, pdb_summary: str, llm_client, config: Dict[str, Any]
) -> str:
    """Rephrase user goal with LLM for clarity."""
    prompt_template = config.get("input_validation", {}).get("goal_rephrase_prompt", "")
    if not prompt_template or not llm_client:
        return user_goal
    
    try:
        from ..utils import log_llm_interaction
        # Format the prompt with actual values
        formatted_prompt = prompt_template.format(user_goal=user_goal, pdb_summary=pdb_summary)
        
        # Send formatted prompt to LLM
        response = llm_client.prompt(
            prompt=formatted_prompt,
            temperature=0.3, max_tokens=300
        )
        
        # Log the FORMATTED prompt (not the template) so it shows actual values
        log_llm_interaction(agent_name="supervisor.goal_rephrasing", prompt=formatted_prompt, response=response)
        return response.strip() if response.strip() and len(response.strip()) > 10 else user_goal
    except Exception:
        return user_goal


def build_human_summary(analysis: Dict[str, Any]) -> str:
    """Build a human-readable summary from PDB analysis."""
    summary_parts = []
    if analysis.get("protein", {}).get("present"):
        summary_parts.append(f"Protein ({analysis.get('protein', {}).get('total_residues', 0)} residues)")
    if analysis.get("ligands", {}).get("present"):
        summary_parts.append(f"Ligands: {', '.join(analysis.get('ligands', {}).get('residue_names', []))}")
    if analysis.get("water", {}).get("present"):
        summary_parts.append(f"Water ({analysis.get('water', {}).get('molecule_count', 0)} molecules)")
    if analysis.get("ions", {}).get("present"):
        ion_types = analysis.get("ions", {}).get("types", {})
        if ion_types:
            summary_parts.append(f"Ions: {', '.join(ion_types.keys())}")
    return " | ".join(summary_parts) if summary_parts else "Unknown structure"


def extract_file_names_from_goal(
    user_goal: str, hpc_dir: str
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract explicit file names from user goal.
    
    Priority:
    1. Use explicitly stated file names from user goal
    2. Default to md.* pattern (md.gro, md.xtc, md.edr)
    3. Return None to trigger auto-discovery
    
    Args:
        user_goal: User's analysis goal
        hpc_dir: HPC output directory path
        
    Returns:
        Tuple of (topology_file, trajectory_file, energy_file) or None values
    """
    topology_file = None
    trajectory_file = None
    energy_file = None
    
    # Pattern to match explicit file names in user goal
    # Examples: "md.xtc", "trajectory.xtc", "topology.gro"
    goal_lower = user_goal.lower()
    
    # Look for topology files (.gro, .pdb, .tpr)
    topo_pattern = r'([\w\-]+\.(?:gro|pdb|tpr))'
    topo_matches = re.findall(topo_pattern, goal_lower)
    if topo_matches:
        # Use the explicitly mentioned file
        candidate = topo_matches[0]
        candidate_path = os.path.join(hpc_dir, candidate)
        if os.path.exists(candidate_path):
            topology_file = candidate_path
    
    # Look for trajectory files (.xtc, .trr)
    traj_pattern = r'([\w\-]+\.(?:xtc|trr))'
    traj_matches = re.findall(traj_pattern, goal_lower)
    if traj_matches:
        # Use the explicitly mentioned file
        candidate = traj_matches[0]
        candidate_path = os.path.join(hpc_dir, candidate)
        if os.path.exists(candidate_path):
            trajectory_file = candidate_path
    
    # Look for energy files (.edr)
    energy_pattern = r'([\w\-]+\.edr)'
    energy_matches = re.findall(energy_pattern, goal_lower)
    if energy_matches:
        candidate = energy_matches[0]
        candidate_path = os.path.join(hpc_dir, candidate)
        if os.path.exists(candidate_path):
            energy_file = candidate_path
    
    # If no explicit files found in goal, default to md.* pattern
    if not topology_file:
        md_gro = os.path.join(hpc_dir, "md.gro")
        md_pdb = os.path.join(hpc_dir, "md.pdb")
        md_tpr = os.path.join(hpc_dir, "md.tpr")
        if os.path.exists(md_gro):
            topology_file = md_gro
        elif os.path.exists(md_pdb):
            topology_file = md_pdb
        elif os.path.exists(md_tpr):
            topology_file = md_tpr
    
    if not trajectory_file:
        md_xtc = os.path.join(hpc_dir, "md.xtc")
        md_trr = os.path.join(hpc_dir, "md.trr")
        if os.path.exists(md_xtc):
            trajectory_file = md_xtc
        elif os.path.exists(md_trr):
            trajectory_file = md_trr
    
    if not energy_file:
        md_edr = os.path.join(hpc_dir, "md.edr")
        if os.path.exists(md_edr):
            energy_file = md_edr
    
    return topology_file, trajectory_file, energy_file


def enrich_analysis_prompt(
    user_goal: str,
    file_info: Dict[str, Any],
    llm_client,
    config: Dict[str, Any]
) -> str:
    """
    Enrich user's analysis goal with validated file information.
    
    Uses LLM to rephrase the user's analysis goal clearly, then adds file details.
    
    Args:
        user_goal: User's natural language analysis goal
        file_info: Available file information (topology, trajectory, etc.)
        llm_client: LLM client for rephrasing
        config: Supervisor configuration
        
    Returns:
        Enriched analysis prompt string
    """
    # Build file summary
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
    
    # Use LLM to rephrase the user's analysis goal with file context
    rephrased_goal = rephrase_analysis_goal_with_llm(user_goal, file_summary, llm_client, config)
    
    # Create enhanced prompt: rephrased goal + file information
    enhanced_prompt = f"{rephrased_goal}\n\n**Available Files:**\n{file_summary}"
    
    return enhanced_prompt.strip()


def rephrase_analysis_goal_with_llm(
    user_goal: str, file_summary: str, llm_client, config: Dict[str, Any]
) -> str:
    """Rephrase analysis goal with LLM for clarity."""
    prompt_template = config.get("input_validation", {}).get("analysis_rephrase_prompt", "")
    if not prompt_template or not llm_client:
        return user_goal
    
    try:
        from ..utils import log_llm_interaction
        # Format the prompt with actual values
        formatted_prompt = prompt_template.format(user_goal=user_goal, file_summary=file_summary)
        
        # Send formatted prompt to LLM
        response = llm_client.prompt(
            prompt=formatted_prompt,
            temperature=0.3, max_tokens=300
        )
        
        # Log the FORMATTED prompt (not the template) so it shows actual values
        log_llm_interaction(
            agent_name="supervisor.analysis_goal_rephrasing",
            prompt=formatted_prompt,
            response=response
        )
        return response.strip() if response.strip() and len(response.strip()) > 10 else user_goal
    except Exception as e:
        logger.warning(f"Failed to rephrase analysis goal with LLM: {e}")
        return user_goal

# Removed detect_subtask_type - subtask is now passed directly via config
# Removed detect_trajectory_paths - trajectory files should be passed as arguments

def detect_task_required_inputs(subtask_type: Optional[str]) -> Dict[str, bool]:
    """Determine which inputs are required based on subtask type."""
    inputs_needed = {
        "pdb_required": True,
        "pdb_analysis_required": True,
        "trajectory_path_required": False,
        "topology_required": False
    }
    
    if subtask_type == "analysis_only":
        inputs_needed.update({"pdb_required": False, "pdb_analysis_required": False,
                             "trajectory_path_required": True, "topology_required": True})
    elif subtask_type in ["setup_only", "preprocess_only"]:
        inputs_needed.update({"pdb_required": True, "pdb_analysis_required": True})
    return inputs_needed


# =============================================================================
# UNIFIED MODULAR FUNCTIONS - Used for ALL task types
# =============================================================================

def rephrase_with_context(
    user_goal: str,
    context_type: str,
    context_data: Dict[str, Any],
    llm_client,
    config: Dict[str, Any]
) -> str:
    """
    Universal LLM rephrasing function that works with any context type.
    
    This replaces the duplicate functions:
    - rephrase_user_goal_with_llm()
    - rephrase_analysis_goal_with_llm()
    
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
        from ..utils import log_llm_interaction
        
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
    
    This replaces the duplicate functions:
    - enrich_user_prompt()
    - enrich_analysis_prompt()
    
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


def validate_and_enrich_inputs(
    state: Dict[str, Any],
    subtask_type: str,
    llm_client,
    config: Dict[str, Any],
    analyze_pdb_tool,
    logger
) -> Dict[str, Any]:
    """
    Universal input validation and enrichment function for ALL task types.
    
    This replaces the duplicate validation methods:
    - input_validation_node() - For PDB-based tasks
    - _validate_analysis_inputs() - For analysis-only tasks
    
    Args:
        state: Current MDState dictionary
        subtask_type: One of "analysis_only", "setup_only", "preprocess_only", "full_task"
        llm_client: LLM client instance
        config: Supervisor configuration
        analyze_pdb_tool: PDB analysis tool (for PDB-based tasks)
        logger: Logger instance
        
    Returns:
        Updated state dictionary with validation results and enriched prompt
    """
    from ..utils import log_agent_action
    
    logger.info("=" * 60)
    logger.info(f"INPUT_VALIDATION: Starting validation for task type: {subtask_type}")
    logger.info("=" * 60)
    
    user_goal = state.get("user_goal", "")
    working_directory = state.get("working_directory", ".")
    
    # Route to appropriate validation based on task type
    if subtask_type == "analysis_only":
        # Analysis-only tasks: validate trajectory/topology files
        state = _validate_analysis_files(state, user_goal, working_directory, llm_client, config, logger)
    else:
        # PDB-based tasks: validate and analyze PDB structure
        state = _validate_pdb_structure(state, user_goal, working_directory, llm_client, config, analyze_pdb_tool, logger)
    
    # Set routing
    state["next_node"] = "supervisor"
    
    logger.info("=" * 60)
    logger.info(f"INPUT_VALIDATION: Validation complete for {subtask_type}")
    logger.info("=" * 60)
    
    return state


def _validate_pdb_structure(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    llm_client,
    config: Dict[str, Any],
    analyze_pdb_tool,
    logger
) -> Dict[str, Any]:
    """Validate PDB structure for setup/preprocess/full tasks."""
    import os
    from ..utils import log_agent_action
    
    # Step 1: Extract PDB filename from user goal
    pdb_pattern = r'([\w\-]+\.pdb)'
    match = re.search(pdb_pattern, user_goal, re.IGNORECASE)
    
    if match:
        pdb_filename = match.group(1)
        pdb_path = os.path.join(working_directory, pdb_filename)
        state["raw_pdb"] = pdb_path
        logger.info(f"INPUT_VALIDATION: Extracted PDB filename: {pdb_filename}")
        logger.info(f"INPUT_VALIDATION: Using working directory: {working_directory}")

        # Validate file exists
        if not os.path.exists(pdb_path):
            state["errors"].append(f"PDB file not found: {pdb_path}")
            logger.error(f"INPUT_VALIDATION: PDB file not found: {pdb_path}")
            return state
    else:
        error_msg = "Could not extract PDB filename from user goal"
        state["errors"].append(error_msg)
        logger.error(f"INPUT_VALIDATION: {error_msg}")
        return state

    # Step 2: Analyze PDB structure
    logger.info(f"INPUT_VALIDATION: Analyzing PDB structure: {pdb_path}")
    
    pdb_analysis_result = analyze_pdb_tool.invoke({"pdb_file": pdb_path})
    
    if not pdb_analysis_result.get("success"):
        error_msg = f"PDB analysis failed: {pdb_analysis_result.get('error', 'Unknown error')}"
        state["warnings"].append(error_msg)
        logger.warning(f"INPUT_VALIDATION: {error_msg}")
        logger.warning("INPUT_VALIDATION: Continuing with limited analysis, will use defaults")
        
        # Create minimal analysis for fallback
        state["pdb_analysis"] = {
            "total_atoms": 0,
            "total_residues": 0,
            "protein": {"present": True},
            "ligands": {"present": False},
            "water": {"present": False},
            "components_available": {},
            "chain_ids": []
        }
    else:
        # Store analysis in state
        state["pdb_analysis"] = pdb_analysis_result.get("analysis", {})
        logger.info(f"INPUT_VALIDATION: PDB analysis complete - {pdb_analysis_result.get('message', '')}")
        
        # Log detailed analysis
        analysis = state["pdb_analysis"]
        
        # Extract protein sequences if available
        protein_sequences = {}
        if analysis.get("protein", {}).get("present"):
            chains_info = analysis.get("protein", {}).get("chains", {})
            for chain_id, chain_data in chains_info.items():
                sequence = chain_data.get("sequence", "")
                if sequence:
                    protein_sequences[chain_id] = sequence
        
        # Build details dict
        details = {
            "file": pdb_path,
            "total_atoms": analysis.get("total_atoms", 0),
            "total_residues": analysis.get("total_residues", 0),
            "components_available": analysis.get("components_available", {})
        }
        
        # Add protein sequences if present
        if protein_sequences:
            details["protein_sequences"] = protein_sequences
        
        log_agent_action(
            agent_name="supervisor.input_validation",
            action="PDB Structure Analysis",
            details=details
        )
    
    # Get analysis for subsequent steps
    analysis = state["pdb_analysis"]

    # Step 3: Parse user intent and determine component selection
    component_selection = parse_component_selection(user_goal, analysis)
    state["component_selection"] = component_selection
    logger.info(f"INPUT_VALIDATION: Component selection: {component_selection}")

    # Step 4: Validate feasibility
    validation_result = validate_feasibility(user_goal, analysis, component_selection)
    
    if not validation_result["is_feasible"]:
        for error in validation_result["errors"]:
            state["errors"].append(error)
            logger.error(f"INPUT_VALIDATION: Feasibility error - {error}")
        return state
    
    for warning in validation_result["warnings"]:
        state["warnings"].append(warning)
        logger.warning(f"INPUT_VALIDATION: {warning}")

    # Step 5: Enrich user prompt with validated information using unified function
    pdb_summary = build_human_summary(analysis)
    enriched_prompt = enrich_prompt_with_context(
        user_goal=user_goal,
        context_type="pdb",
        context_data={
            "pdb_analysis": analysis,
            "pdb_summary": pdb_summary
        },
        llm_client=llm_client,
        config=config
    )
    state["structured_prompt"] = enriched_prompt
    state["rephrased_goal"] = enriched_prompt
    
    logger.info(f"INPUT_VALIDATION: Enriched prompt created: {enriched_prompt[:150]}...")
    
    log_agent_action(
        agent_name="supervisor.input_validation",
        action="Input Validation Complete",
        details={
            "original_goal": user_goal[:100],
            "enriched_prompt": enriched_prompt[:300],
            "pdb_file": pdb_path,
            "working_directory": working_directory
        }
    )

    # Log final validation summary
    logger.info(f"  - PDB Analysis: {'✓ Success' if not state.get('warnings') else '⚠ With warnings'}")
    logger.info(f"  - Component Selection: {component_selection}")
    logger.info(f"  - Working Directory: {working_directory}")
    logger.info(f"  - Enriched Prompt: {enriched_prompt[:80]}...")
    
    return state


def _validate_analysis_files(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    llm_client,
    config: Dict[str, Any],
    logger
) -> Dict[str, Any]:
    """Validate trajectory/topology files for analysis-only tasks."""
    import os
    from ..utils import log_agent_action
    
    hpc_output_dir = os.path.join(working_directory, "hpc")
    analysis_output_dir = os.path.join(working_directory, "analysis")
    
    # Step 1: Validate HPC output directory exists
    if not os.path.exists(hpc_output_dir):
        error = f"HPC output directory not found: {hpc_output_dir}"
        state["errors"].append(error)
        logger.error(f"INPUT_VALIDATION: {error}")
        return state
    
    logger.info(f"INPUT_VALIDATION: ✓ HPC output directory found: {hpc_output_dir}")
    
    # Step 2: Discover/validate files (prioritize explicit files from user goal)
    topology_file, trajectory_file, energy_file = extract_file_names_from_goal(
        user_goal, hpc_output_dir
    )
    
    logger.info("INPUT_VALIDATION: File discovery strategy:")
    logger.info("  1. Use explicitly stated files in user goal")
    logger.info("  2. Default to md.* pattern (md.gro, md.xtc, md.edr)")
    logger.info("  3. Auto-discover first available file as fallback")
    
    # If explicit/default files not found, fall back to auto-discovery
    if not topology_file or not trajectory_file:
        logger.info("INPUT_VALIDATION: No explicit/default files found, attempting auto-discovery...")
        
        topology_extensions = [".gro", ".pdb", ".tpr"]
        trajectory_extensions = [".xtc", ".trr"]
        energy_extensions = [".edr"]
        
        try:
            hpc_files = os.listdir(hpc_output_dir)
            
            # Find topology file if not already set
            if not topology_file:
                for ext in topology_extensions:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        topology_file = os.path.join(hpc_output_dir, matching[0])
                        logger.info(f"INPUT_VALIDATION: ⚠ Auto-discovered topology: {matching[0]}")
                        break
            
            # Find trajectory file if not already set
            if not trajectory_file:
                for ext in trajectory_extensions:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        trajectory_file = os.path.join(hpc_output_dir, matching[0])
                        logger.info(f"INPUT_VALIDATION: ⚠ Auto-discovered trajectory: {matching[0]}")
                        break
            
            # Find energy file if not already set (optional)
            if not energy_file:
                for ext in energy_extensions:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        energy_file = os.path.join(hpc_output_dir, matching[0])
                        logger.info(f"INPUT_VALIDATION: ⚠ Auto-discovered energy: {matching[0]}")
                        break
                    
        except Exception as e:
            error = f"Failed to list files in {hpc_output_dir}: {e}"
            state["errors"].append(error)
            logger.error(f"INPUT_VALIDATION: {error}")
            return state
    else:
        logger.info(f"INPUT_VALIDATION: ✓ Using explicit/default topology: {os.path.basename(topology_file)}")
        logger.info(f"INPUT_VALIDATION: ✓ Using explicit/default trajectory: {os.path.basename(trajectory_file)}")
        if energy_file:
            logger.info(f"INPUT_VALIDATION: ✓ Using explicit/default energy: {os.path.basename(energy_file)}")
    
    # Store in file_info dict
    file_info = {
        "hpc_output_dir": hpc_output_dir,
        "analysis_output_dir": analysis_output_dir,
        "topology_file": topology_file,
        "trajectory_file": trajectory_file,
        "energy_file": energy_file
    }
    
    # Step 3: Validate that required files were found
    if not file_info["topology_file"]:
        warning = f"No topology file (.gro, .pdb, .tpr) found in {hpc_output_dir}"
        state["warnings"].append(warning)
        logger.warning(f"INPUT_VALIDATION: {warning}")
    
    if not file_info["trajectory_file"]:
        warning = f"No trajectory file (.xtc, .trr) found in {hpc_output_dir}"
        state["warnings"].append(warning)
        logger.warning(f"INPUT_VALIDATION: {warning}")
    
    # Step 4: Enrich user prompt with validated information using unified function
    enriched_prompt = enrich_prompt_with_context(
        user_goal=user_goal,
        context_type="files",
        context_data={"file_info": file_info},
        llm_client=llm_client,
        config=config
    )
    state["structured_prompt"] = enriched_prompt
    state["rephrased_goal"] = enriched_prompt
    
    logger.info(f"INPUT_VALIDATION: Enriched analysis prompt created: {enriched_prompt[:150]}...")
    
    # Step 5: Store analysis context in state
    state["pdb_analysis"] = {
        "subtask_type": "analysis_only",
        "requires_pdb_structure": False,
        "working_directory": working_directory,
        "hpc_output_dir": hpc_output_dir,
        "analysis_output_dir": analysis_output_dir,
        "topology_file": file_info["topology_file"],
        "trajectory_file": file_info["trajectory_file"],
        "energy_file": file_info["energy_file"]
    }
    
    # CRITICAL: Also set top-level state fields that analysis agent expects
    state["topology"] = file_info["topology_file"]
    state["trajectory_path"] = file_info["trajectory_file"]
    state["energy_file"] = file_info["energy_file"]
    state["hpc_output_directory"] = hpc_output_dir
    
    # Create analysis output directory if it doesn't exist
    os.makedirs(analysis_output_dir, exist_ok=True)
    logger.info(f"INPUT_VALIDATION: ✓ Analysis output directory ready: {analysis_output_dir}")
    
    log_agent_action(
        agent_name="supervisor.input_validation-analysis",
        action="Analysis-Only Input Validation Complete",
        details={
            "subtask_type": "analysis-only",
            "original_goal": user_goal[:100],
            "enriched_prompt": enriched_prompt[:300],
            "topology_file": file_info["topology_file"],
            "trajectory_file": file_info["trajectory_file"],
            "energy_file": file_info["energy_file"],
            "hpc_output_directory": hpc_output_dir,
            "working_directory": working_directory
        }
    )
    
    # Log final validation summary
    logger.info(f"  - File Validation: {'✓ Success' if not state.get('errors') else '✗ Failed'}")
    logger.info(f"  - Topology: {file_info['topology_file'] or 'Not found'}")
    logger.info(f"  - Trajectory: {file_info['trajectory_file'] or 'Not found'}")
    logger.info(f"  - Working Directory: {working_directory}")
    logger.info(f"  - Enriched Prompt: {enriched_prompt[:80]}...")
    
    return state