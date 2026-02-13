"""
Supervisor Helper Tools

Utility functions for input validation, component parsing, and prompt enrichment.
"""

import logging
import re
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def extract_pdb_path(user_goal: str, search_patterns: list) -> Optional[str]:
    """
    Extract PDB file path from user goal using regex patterns.
    
    Args:
        user_goal: User's natural language goal
        search_patterns: List of regex patterns to search for PDB paths
        
    Returns:
        PDB file path if found, None otherwise
    """
    for pattern in search_patterns:
        match = re.search(pattern, user_goal)
        if match:
            pdb_path = match.group(1)
            logger.info(f"Matched PDB path with pattern '{pattern}': {pdb_path}")
            return pdb_path
    
    logger.warning("No PDB file path found in user goal")
    return None


def parse_component_selection(user_goal: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse user intent to determine which components to include in simulation.
    
    Key principle: Respect user's EXPLICIT requests first, then fall back to PDB contents.
    
    Args:
        user_goal: User's natural language goal
        analysis: PDB analysis results
        
    Returns:
        Dict with component selection (protein, ligand, water, ions, etc.)
    """
    goal_lower = user_goal.lower()
    
    # Initialize with explicit user requests (defaults to None = not specified)
    explicit_requests = {
        "protein": None,
        "ligand": None,
        "water": None,
        "ions": None,
        "specific_chains": None
    }
    
    # Parse EXPLICIT user intent for specific component requests
    # Look for "only" keywords which are strongest indicators
    if any(phrase in goal_lower for phrase in ["only protein", "just protein", "protein only", "extract protein"]):
        explicit_requests["protein"] = True
        explicit_requests["ligand"] = False
        explicit_requests["ions"] = False
        explicit_requests["water"] = False
        logger.info("User explicitly requested ONLY protein")
    
    # NEW: If user mentions "protein" or "the protein" without mentioning other components, 
    # assume they want protein only (conservative default)
    elif any(phrase in goal_lower for phrase in [
        "of protein", "the protein", "protein structure", "protein system"
    ]):
        # Check if they also mention other components
        mentions_ligand = any(word in goal_lower for word in ["ligand", "atp", "adp", "nad", "fad", "hem"])
        mentions_ions = any(word in goal_lower for word in ["ion", "mg", "ca", "zn", "na", "cl", "mg2+", "ca2+"])
        
        if not mentions_ligand and not mentions_ions:
            # They only mentioned protein, so default to protein only
            explicit_requests["protein"] = True
            explicit_requests["ligand"] = False
            explicit_requests["ions"] = False
            explicit_requests["water"] = False
            logger.info("User mentioned 'protein' without mentioning ligands/ions - defaulting to protein only")
        else:
            # They mentioned protein AND other components, so include what they mentioned
            explicit_requests["protein"] = True
            if mentions_ligand:
                logger.info("User mentioned protein and ligand")
            if mentions_ions:
                logger.info("User mentioned protein and ions")
        
    elif any(phrase in goal_lower for phrase in ["only ligand", "just ligand", "ligand only", "extract ligand"]):
        explicit_requests["protein"] = False
        explicit_requests["ligand"] = True
        explicit_requests["ions"] = False
        explicit_requests["water"] = False
        logger.info("User explicitly requested ONLY ligand")
        
    elif any(phrase in goal_lower for phrase in ["protein-ligand", "complex", "protein and ligand"]):
        explicit_requests["protein"] = True
        explicit_requests["ligand"] = True
        logger.info("User explicitly requested protein-ligand complex")
    
    # Check for explicit component inclusions
    if any(phrase in goal_lower for phrase in [
        "with ligand", "include ligand", "retaining ligand", "retain ligand", 
        "keeping ligand", "keep ligand", "retaining the atp", "retain the atp",
        "retaining atp", "retain atp"
    ]):
        explicit_requests["ligand"] = True
        logger.info("User explicitly wants to include ligand")
    
    if any(phrase in goal_lower for phrase in [
        "with water", "include water", "keep water", "retaining water", "retain water"
    ]):
        explicit_requests["water"] = True
        logger.info("User explicitly wants to include water")
    
    if any(phrase in goal_lower for phrase in [
        "with ions", "include ions", "with ion", "include ion",
        "retaining ions", "retain ions", "retaining the ions", "retain the ions",
        "keeping ions", "keep ions", "retaining mg", "retain mg"
    ]):
        explicit_requests["ions"] = True
        logger.info("User explicitly wants to include ions")
    
    # Check for explicit exclusions
    if "without ligand" in goal_lower or "remove ligand" in goal_lower or "no ligand" in goal_lower:
        explicit_requests["ligand"] = False
        logger.info("User explicitly wants to exclude ligand")
    
    if "without water" in goal_lower or "remove water" in goal_lower or "no water" in goal_lower:
        explicit_requests["water"] = False
        logger.info("User explicitly wants to exclude water")
    
    if "without ions" in goal_lower or "remove ions" in goal_lower or "no ions" in goal_lower:
        explicit_requests["ions"] = False
        logger.info("User explicitly wants to exclude ions")
    
    # Check for specific chain selection (e.g., "chain A", "chain B and C")
    chain_match = re.search(r"chain\s+([A-Z](?:\s+and\s+[A-Z]|,\s*[A-Z])*)", user_goal, re.IGNORECASE)
    if chain_match:
        chain_str = chain_match.group(1)
        chains = re.findall(r"[A-Z]", chain_str.upper())
        explicit_requests["specific_chains"] = chains
        logger.info(f"Specific chain selection detected: {chains}")
    
    # Build final selection: use explicit requests if specified, otherwise fall back to PDB contents
    selection = {
        "protein": explicit_requests["protein"] if explicit_requests["protein"] is not None 
                  else analysis.get("protein", {}).get("present", False),
        "ligand": explicit_requests["ligand"] if explicit_requests["ligand"] is not None
                 else analysis.get("ligands", {}).get("present", False),
        "water": explicit_requests["water"] if explicit_requests["water"] is not None
                else False,  # Default to False - usually removed during preprocessing
        "ions": explicit_requests["ions"] if explicit_requests["ions"] is not None
               else analysis.get("ions", {}).get("present", False),
        "specific_chains": explicit_requests["specific_chains"]
    }
    
    logger.info(f"Final component selection: {selection}")
    return selection


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
    user_goal: str, 
    pdb_summary: str,
    llm_client,
    config: Dict[str, Any]
) -> str:
    """
    Use LLM to rephrase user's goal into a clear, unambiguous statement.
    
    Args:
        user_goal: Original user goal
        pdb_summary: Human-readable PDB structure summary
        llm_client: LLM client instance
        config: Supervisor configuration
        
    Returns:
        Rephrased goal as a clear statement
    """
    logger.info("Attempting to rephrase user goal with LLM")
    
    # Get prompt template from config
    prompt_template = config.get("input_validation", {}).get("goal_rephrase_prompt", "")
    
    if not prompt_template:
        logger.warning("No goal_rephrase_prompt in config, using original goal")
        return user_goal
    
    # Check if LLM client is available
    if not llm_client:
        logger.warning("No LLM client available, using original goal")
        return user_goal
    
    # Format the prompt
    prompt = prompt_template.format(
        user_goal=user_goal,
        pdb_summary=pdb_summary
    )
    
    # Call LLM
    try:
        from ..utils import log_llm_interaction
        
        logger.info("Calling LLM for goal rephrasing")
        response = llm_client.prompt(
            prompt=prompt,
            temperature=0.3,
            max_tokens=300
        )
        
        log_llm_interaction(
            agent_name="supervisor.goal_rephrasing",
            prompt=prompt,
            response=response
        )
        
        rephrased = response.strip()
        
        # Basic validation - if LLM returns empty or very short, use original
        if not rephrased or len(rephrased) < 10:
            logger.warning("LLM returned empty/short response, using original goal")
            return user_goal
        
        logger.info(f"Successfully rephrased goal: {rephrased[:150]}...")
        return rephrased
        
    except Exception as e:
        logger.error(f"LLM rephrasing failed: {e}", exc_info=True)
        logger.warning("Falling back to original goal")
        return user_goal


def build_human_summary(analysis: Dict[str, Any]) -> str:
    """
    Build a human-readable summary from PDB analysis if not available.
    
    Args:
        analysis: PDB analysis results
        
    Returns:
        Human-readable summary string
    """
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
    
    return " | ".join(summary_parts) if summary_parts else "Unknown structure"
