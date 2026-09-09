"""
Component Parser and Feasibility Validator for Supervisor

Analyzes user goals and PDB structures to determine component selection and feasibility.
"""
import re
from typing import Any, Dict, List, Optional


def _normalize_goal_text(text: str) -> str:
    """Lowercase and normalize unicode hyphens for robust phrase matching."""
    p = (text or "").lower()
    return (
        p.replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )


def _label_ligand_suffix(label: str) -> Optional[str]:
    """Return decisive ligand/ion suffix from a sim label, if present.

    Examples:
      jak2_atp_2mg_ATP_MG → ATP_MG
      jak2_atp_2mg_ATP    → ATP
      jak2_atp_2mg        → None  (bare stem; '2mg' is part of the PDB name)
    """
    name = (label or "").strip()
    if not name:
        return None
    upper = name.upper()
    if upper.endswith("_ATP_MG"):
        return "ATP_MG"
    if upper.endswith("_ATP"):
        return "ATP"
    return None


def _excludes_crystallographic_ions(text: str) -> bool:
    """True when the case text explicitly excludes MG / crystallographic ions."""
    t = _normalize_goal_text(text)
    if re.search(
        r"\b(?:no|without|exclude|excluding|remove|drop|omit)\s+"
        r"(?:mg(?:2\+?|\u00b2\+?)?|magnesium|ions?|cofactors?)\b",
        t,
    ):
        return True
    # "ATP only" / "ligand only" implies no crystallographic ions unless Mg is
    # also requested positively elsewhere.
    if re.search(r"\b(?:atp|ligand)\s+only\b", t) and not re.search(
        r"\b(?:with|plus|\+|and)\s+mg(?:2\+?|\u00b2\+?)?\b", t
    ):
        return True
    return False


def _wants_crystallographic_ions(sim_case: Optional[Dict[str, Any]], text: str) -> bool:
    """Decide whether a protein_with_ligand case should keep crystallographic ions.

    Label suffix is authoritative when present (``*_ATP`` vs ``*_ATP_MG``).
    Otherwise use positive/negative phrasing — never treat ``no Mg`` as wanting MG,
    and never treat ``2mg`` inside a PDB stem as an ion request.
    """
    label = str((sim_case or {}).get("label") or "")
    suffix = _label_ligand_suffix(label)
    if suffix == "ATP_MG":
        return True
    if suffix == "ATP":
        return False

    t = _normalize_goal_text(text)
    if _excludes_crystallographic_ions(t):
        return False

    # Positive ion / Mg signals only (word boundaries; avoid matching '2mg' stems).
    if re.search(r"(?:_atp_mg\b|\batp_mg\b)", t):
        return True
    if re.search(
        r"\b(?:with|plus|include|keep|retain|and)\s+mg(?:2\+?|\u00b2\+?)?\b"
        r"|\bmg(?:2\+?|\u00b2\+?)?\s+(?:ions?|and)\b"
        r"|\batp\s*\+\s*mg\b"
        r"|\bprotein\s*\+\s*atp\s*\+\s*mg\b",
        t,
    ):
        return True
    if re.search(
        r"\b(?:with|include|keep|retain)\s+(?:crystallographic\s+)?ions?\b"
        r"|\bcofactors?\b",
        t,
    ):
        return True
    # Default for bare protein_with_ligand: ligand yes, crystallographic ions no.
    return False


def detect_component_cases(
    user_goal: str,
    enriched_prompt: str = "",
    *,
    pdb_count: int = 0,
) -> List[Dict[str, str]]:
    """
    Infer component-specific simulation cases from user goal text.

    When the user requests multiple systems per PDB (e.g. apo + holo), returns
    one case dict per variant. Otherwise returns a single default case.

    Uses the original user goal only; enriched/rephrased prompts are ignored
    because technical details (e.g. "1.2 nm buffer") cause false apo+holo splits.
    """
    from .component_case_resolver import heuristic_component_cases

    return heuristic_component_cases(user_goal, pdb_count=pdb_count)


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
    # Normalize common unicode hyphens so phrase matching is robust.
    goal_lower = (
        goal_lower
        .replace("\u2011", "-")
        .replace("\u2012", "-")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
        .replace("\u2212", "-")
    )
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
    elif any(p in goal_lower for p in [
        "only protein", "just protein", "protein only", "protein-only", "protein alone", "extract protein"
    ]):
        explicit.update({"protein": True, "ligand": False, "ions": False, "water": False})
    elif any(p in goal_lower for p in ["only ligand", "just ligand", "ligand only", "extract ligand"]):
        explicit.update({"protein": False, "ligand": True, "ions": False, "water": False})
    elif "complex" in goal_lower or "protein and ligand" in goal_lower:
        explicit.update({"protein": True, "ligand": True})
    
    # ── Explicit inclusion overrides ─────────────────────────────────────────
    if any(p in goal_lower for p in [
        "with ligand", "with ligands", "include ligand", "include ligands",
        "retaining ligand", "retaining ligands", "retain ligand", "retain ligands",
        "keeping ligand", "keeping ligands", "keep ligand", "keep ligands"
    ]):
        explicit["ligand"] = True
    if any(p in goal_lower for p in ["with water", "include water", "keep water", "retaining water", "retain water"]):
        explicit["water"] = True
    if any(p in goal_lower for p in [
        "with ion", "with ions", "include ion", "include ions",
        "retaining ion", "retaining ions", "retain ion", "retain ions",
        "keeping ion", "keeping ions", "keep ion", "keep ions"
    ]):
        explicit["ions"] = True
    
    # ── Explicit exclusion overrides ─────────────────────────────────────────
    if any(p in goal_lower for p in [
        "without ligand", "without ligands", "remove ligand", "remove ligands", "no ligand", "no ligands",
        "remove atp", "without atp", "exclude atp", "drop atp"
    ]):
        explicit["ligand"] = False
    if any(p in goal_lower for p in ["without water", "remove water", "no water"]):
        explicit["water"] = False
    if any(p in goal_lower for p in [
        "without ion", "without ions", "remove ion", "remove ions", "no ion", "no ions",
        "remove mg", "without mg", "exclude mg", "drop mg", "no mg", "no magnesium",
    ]):
        explicit["ions"] = False
    # Broader phrasing: "exclude crystallographic Mg/ions", "remove all Mg ions"
    if re.search(
        r"(?:exclude|excluding|remove|drop|omit|strip).{0,48}\b(?:mg(?:2\+?|\u00b2\+?)?|magnesium|ions?)\b"
        r"|\b(?:mg(?:2\+?|\u00b2\+?)?|ions?).{0,24}(?:excluded|removed|omitted)\b",
        goal_lower,
    ):
        explicit["ions"] = False
    # Label / case_id embedded in per-sim goals (parallel workers).
    if re.search(r"case_id\s*=\s*protein_only\b", goal_lower):
        explicit.update({"protein": True, "ligand": False, "ions": False, "water": False})
    elif re.search(r"_atp(?!_mg)\b", goal_lower) and re.search(
        r"case_id\s*=\s*protein_with_ligand\b", goal_lower
    ):
        # *_ATP (not *_ATP_MG) with protein_with_ligand → ligand yes, crystal ions no
        if not re.search(r"_atp_mg\b", goal_lower):
            explicit["ligand"] = True
            if _excludes_crystallographic_ions(goal_lower) or "atp only" in goal_lower:
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


def apply_sim_case_to_component_selection(
    selection: Dict[str, Any],
    sim_case: Optional[Dict[str, Any]],
    analysis: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Override component selection using multi-sim case metadata.

    PDB analysis alone cannot distinguish apo vs holo when both share one source
    structure that contains ligand/ions. ``case_id`` from the master plan is the
    authoritative signal for which PDB components to keep.
    """
    if not sim_case:
        return selection

    updated = dict(selection or {})
    case_id = str(sim_case.get("case_id") or "").strip()
    text = _normalize_goal_text(
        " ".join(
            str(sim_case.get(k) or "")
            for k in ("label", "case_description", "case_directive")
        )
    )

    if case_id == "protein_only":
        updated.update(
            {
                "protein": True,
                "ligand": False,
                "ions": False,
                "water": False,
            }
        )
        return updated

    if case_id == "protein_with_ligand":
        updated["protein"] = True
        updated["ligand"] = True
        # Keep crystallographic ions only when the case/label asks for them
        # (e.g. *_ATP_MG). "ATP only (no Mg)" and *_ATP must exclude MG even
        # when the shared source PDB contains ions.
        updated["ions"] = _wants_crystallographic_ions(sim_case, text)
        return updated

    return updated


def append_sim_case_requirement(prompt: str, sim_info: Optional[Dict[str, Any]]) -> str:
    """Ensure case_id / case_directive appear in a per-sim goal or prompt string."""
    text = (prompt or "").strip()
    if not sim_info:
        return text
    case_id = str(sim_info.get("case_id") or "").strip()
    directive = str(sim_info.get("case_directive") or "").strip()
    description = str(sim_info.get("case_description") or "").strip()
    if not case_id and not directive:
        return text

    lower = text.lower()
    parts = []
    if case_id and f"case_id={case_id}".lower() not in lower and f"case_id: {case_id}".lower() not in lower:
        parts.append(f"case_id={case_id}")
    if description and description.lower() not in lower:
        parts.append(description)
    if directive and directive.lower() not in lower:
        parts.append(directive)
    if case_id == "protein_only" and "exclude ligand" not in lower and "protein only" not in lower:
        parts.append(
            "Use protein only: exclude ligand and crystallographic ions from the source PDB."
        )
    if case_id == "protein_with_ligand":
        case_blob = {
            "label": sim_info.get("label"),
            "case_description": description,
            "case_directive": directive,
            "case_id": case_id,
        }
        case_text = _normalize_goal_text(
            " ".join(str(sim_info.get(k) or "") for k in ("label", "case_description", "case_directive"))
        )
        if _wants_crystallographic_ions(case_blob, case_text):
            if "include" not in lower or "mg" not in lower:
                parts.append(
                    "Include the ligand and crystallographic Mg/ions from the source PDB."
                )
        else:
            if "exclude" not in lower and "no mg" not in lower:
                parts.append(
                    "Include the ligand (e.g. ATP) but exclude crystallographic Mg/ions "
                    "from the source PDB."
                )
    if not parts:
        return text
    return f"{text} Case requirement: {' '.join(parts)}".strip()


def parse_sim_case_requirements(
    label: str = "",
    case_description: str = "",
    case_directive: str = "",
    user_goal: str = "",
    case_id: str = "",
) -> Dict[str, Any]:
    """
    Infer required structural components for a multi-simulation case.

    Example: label p21860_ATP_MG requires protein + ATP ligand + MG ion.
    Prefer explicit ``case_id`` from the master plan when present.
    """
    case_id = str(case_id or "").strip()
    text = _normalize_goal_text(
        f"{label} {case_description} {case_directive} {user_goal}"
    )
    sim_case = {
        "label": label,
        "case_id": case_id,
        "case_description": case_description,
        "case_directive": case_directive,
    }

    requirements = {
        "protein": True,
        "ligand": False,
        "ions": False,
        "ligand_resnames": [],
        "ion_resnames": [],
        "case_type": "default",
    }

    if case_id == "protein_only" or any(
        token in text
        for token in (
            "protein only",
            "protein-only",
            "protein alone",
            "apoprotein",
            "apo protein",
        )
    ):
        # Do not treat "protein only" inside a longer holo description as apo when
        # case_id explicitly says protein_with_ligand.
        if case_id != "protein_with_ligand":
            requirements["case_type"] = "protein_only"
            return requirements

    suffix = _label_ligand_suffix(label)
    wants_ions = _wants_crystallographic_ions(sim_case, text)

    if (
        case_id == "protein_with_ligand"
        or suffix in ("ATP", "ATP_MG")
        or re.search(r"\bprotein\s*\+\s*atp\b", text)
        or ("atp" in text and "protein" in text and case_id != "protein_only")
    ):
        requirements.update(
            {
                "ligand": True,
                "ligand_resnames": ["ATP"],
                "case_type": "holo_atp_mg" if wants_ions else "holo_ligand",
            }
        )
        if wants_ions:
            requirements["ions"] = True
            requirements["ion_resnames"] = ["MG"]
        else:
            requirements["ions"] = False
            requirements["ion_resnames"] = []
        return requirements

    return requirements


def validate_sim_case_components(
    analysis: Dict[str, Any],
    requirements: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate that a source PDB contains components required by a sim case."""
    errors = []
    warnings = []

    if requirements.get("protein") and not analysis.get("protein", {}).get("present"):
        errors.append("Missing required protein in source structure")

    if requirements.get("ligand"):
        ligands = analysis.get("ligands", {})
        if not ligands.get("present"):
            errors.append("Missing required ligand in source structure")
        else:
            available = {name.upper() for name in ligands.get("residue_names", [])}
            for resname in requirements.get("ligand_resnames", ["ATP"]):
                if resname.upper() not in available:
                    errors.append(
                        f"Missing required ligand {resname} in source structure "
                        f"(found: {sorted(available) or 'none'})"
                    )

    if requirements.get("ions"):
        ions = analysis.get("ions", {})
        if not ions.get("present"):
            errors.append("Missing required ion in source structure")
        else:
            available = {name.upper() for name in (ions.get("types") or {}).keys()}
            for resname in requirements.get("ion_resnames", ["MG"]):
                if resname.upper() not in available:
                    errors.append(
                        f"Missing required ion {resname} in source structure "
                        f"(found: {sorted(available) or 'none'})"
                    )

    return {
        "is_feasible": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "requirements": requirements,
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

    if component_selection.get("ions") and not analysis.get("ions", {}).get("present"):
        errors.append("User requested ion simulation but PDB contains no ions")
    
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
