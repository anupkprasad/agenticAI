"""
Component Parser and Feasibility Validator for Supervisor

Analyzes user goals and PDB structures to determine component selection and feasibility.
"""
import re
from typing import Dict, Any


def parse_component_selection(user_goal: str, analysis: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse user intent to determine components for simulation.
    
    Supports compound phrases like "protein-ligand-ions", "protein-ligand",
    "protein only", "protein and ligand", etc.
    
    Args:
        user_goal: User's natural language goal
        analysis: PDB analysis results
        
    Returns:
        Dict with protein, ligand, water, ions, specific_chains selections
    """
    goal_lower = user_goal.lower()
    explicit = {component: None for component in ["protein", "ligand", "water", "ions", "specific_chains"]}
    
    # ── Detect compound component phrases (e.g. "protein-ligand-ions") ───────
    # These hyphenated or "and"-joined phrases explicitly enumerate requested components.
    # Match patterns like: "of protein-ligand-ions", "for protein-ligand", 
    # "setup protein, ligand and ions", "protein and ligand and ions"
    compound_pattern = re.search(
        r'(?:of|for|setup|simulate|simulation\s+(?:of|for))\s+'
        r'((?:protein|ligand|ions?|water|complex)'
        r'(?:\s*[-,/&]\s*(?:protein|ligand|ions?|water|complex)'
        r'|\s+and\s+(?:protein|ligand|ions?|water|complex))+)',
        goal_lower
    )
    
    if compound_pattern:
        compound_str = compound_pattern.group(1)
        # Split on hyphens, commas, slashes, ampersands, and "and"
        parts = re.split(r'\s*[-,/&]\s*|\s+and\s+', compound_str)
        parts = [p.strip() for p in parts if p.strip()]
        
        # Start with everything False, then enable only mentioned components
        explicit.update({"protein": False, "ligand": False, "ions": False, "water": False})
        for part in parts:
            if "protein" in part:
                explicit["protein"] = True
            elif "ligand" in part:
                explicit["ligand"] = True
            elif "ion" in part:
                explicit["ions"] = True
            elif "water" in part:
                explicit["water"] = True
            elif "complex" in part:
                # "complex" implies protein + ligand
                explicit["protein"] = True
                explicit["ligand"] = True
    
    # ── Single-component "only" / "just" requests ───────────────────────────
    # These override compound detection because the user is being very specific.
    elif any(p in goal_lower for p in ["only protein", "just protein", "protein only", "extract protein"]):
        explicit.update({"protein": True, "ligand": False, "ions": False, "water": False})
    elif any(p in goal_lower for p in ["only ligand", "just ligand", "ligand only", "extract ligand"]):
        explicit.update({"protein": False, "ligand": True, "ions": False, "water": False})
    elif "complex" in goal_lower or "protein and ligand" in goal_lower:
        explicit.update({"protein": True, "ligand": True})
    
    # ── Explicit inclusion overrides ─────────────────────────────────────────
    if any(p in goal_lower for p in ["with ligand", "include ligand", "retaining ligand", "retain ligand", "keeping ligand", "keep ligand"]):
        explicit["ligand"] = True
    if any(p in goal_lower for p in ["with water", "include water", "keep water", "retaining water", "retain water"]):
        explicit["water"] = True
    if any(p in goal_lower for p in ["with ions", "include ions", "retaining ions", "retain ions", "keeping ions", "keep ions"]):
        explicit["ions"] = True
    
    # ── Explicit exclusion overrides ─────────────────────────────────────────
    if any(p in goal_lower for p in ["without ligand", "remove ligand", "no ligand"]):
        explicit["ligand"] = False
    if any(p in goal_lower for p in ["without water", "remove water", "no water"]):
        explicit["water"] = False
    if any(p in goal_lower for p in ["without ions", "remove ions", "no ions"]):
        explicit["ions"] = False
    
    # ── Check specific chains ────────────────────────────────────────────────
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
        warnings.append("PDB is missing hydrogens - preprocessing will add them")
    
    if components.get("alternate_locations"):
        warnings.append("PDB has alternate locations - preprocessing will select first conformation")
    
    return {
        "is_feasible": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }


def build_human_summary(analysis: Dict[str, Any]) -> str:
    """
    Build human-readable summary of PDB analysis for LLM context.
    
    Args:
        analysis: PDB analysis dict
        
    Returns:
        Human-readable summary string
    """
    summary_parts = []
    
    if analysis.get("protein", {}).get("present"):
        chains_info = analysis.get("protein", {}).get("chains", {})
        if chains_info:
            summary_parts.append(f"Protein ({len(chains_info)} chains)")
        else:
            summary_parts.append("Protein")
    
    if analysis.get("ligands", {}).get("present"):
        ligand_names = analysis.get("ligands", {}).get("residue_names", [])
        if ligand_names:
            summary_parts.append(f"Ligands: {', '.join(ligand_names)}")
    
    if analysis.get("ions", {}).get("present"):
        ion_types = analysis.get("ions", {}).get("types", {})
        if ion_types:
            summary_parts.append(f"Ions: {', '.join(ion_types.keys())}")
    
    return " | ".join(summary_parts) if summary_parts else "Unknown structure"
