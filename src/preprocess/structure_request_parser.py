"""
Parse structure acquisition requests from natural language goals.

Extracts UniProt IDs, protein names, domain labels, and residue ranges so the
preprocess agent can download and trim structures without an existing PDB file.

When a domain is named without explicit residues (e.g. "kinase domain"),
residue boundaries are resolved from UniProt feature annotations.
"""
import re
from typing import Any, Dict, List, Optional, Tuple

from .domain_sources import lookup_domain_range


def _normalize_uniprot(raw: str) -> str:
    return raw.strip().upper()


def extract_uniprot_ids(text: str) -> List[str]:
    """Extract UniProt accessions from free text."""
    if not text:
        return []

    patterns = [
        r"\buniprot(?:\s*id)?\s*[:=]?\s*([a-z][0-9][a-z0-9]{3,8})\b",
        r"\buniprotid\s+([a-z][0-9][a-z0-9]{3,8})\b",
        r"\b([a-z][0-9][a-z0-9]{3,8})\s*:\s*[A-Z][A-Z0-9_]+\b",  # p21860: ERBB3
        r"\b([a-z][0-9][a-z0-9]{3,8})\.pdb\b",
    ]
    found = []
    lower = text.lower()
    for pattern in patterns:
        for match in re.finditer(pattern, lower, re.IGNORECASE):
            found.append(_normalize_uniprot(match.group(1)))

    seen = set()
    unique = []
    for uid in found:
        if uid not in seen:
            seen.add(uid)
            unique.append(uid)
    return unique


def extract_protein_name(text: str, uniprot_id: Optional[str] = None) -> Optional[str]:
    """Extract a human-readable protein name (e.g. ERBB3) from text."""
    if not text:
        return None

    _SKIP = {
        "domain", "kinase", "loop", "region", "residue", "residues", "uniprot",
        "activation", "catalytic", "segment",
    }

    if uniprot_id:
        for pattern in (
            rf"\b{re.escape(uniprot_id)}\s*:\s*([A-Za-z][A-Za-z0-9_]+)\b",
            rf"\b(?:protein|of)\s+([A-Za-z][A-Za-z0-9_]+)\b[^.]*\b{re.escape(uniprot_id)}\b",
            rf"\b{re.escape(uniprot_id)}\b[^.]*\b(?:protein)\s+([A-Za-z][A-Za-z0-9_]+)\b",
        ):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).upper()
                if name.lower() not in _SKIP:
                    return name

    match = re.search(
        r"\bprotein\s+([A-Za-z][A-Za-z0-9_]{2,})\b",
        text,
        re.IGNORECASE,
    )
    if match:
        name = match.group(1).upper()
        if name.lower() not in _SKIP:
            return name

    return None


def extract_domain_label(text: str) -> Optional[str]:
    """Extract domain description such as 'kinase domain'."""
    if not text:
        return None

    patterns = [
        r"\b(kinase\s+domain)\b",
        r"\b(catalytic\s+domain)\b",
        r"\b(activation\s+loop)\b",
        r"\b(sh2\s+domain)\b",
        r"\b(sh3\s+domain)\b",
        r"\b([a-z][a-z0-9_\-]+\s+domain)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            label = match.group(1).strip().lower().replace(" ", "_")
            return label
    return None


def extract_residue_range(text: str) -> Optional[Tuple[int, int]]:
    """
    Extract residue range from patterns like resid 503:771 globally in text.
    """
    if not text:
        return None

    patterns = [
        r"\bresid(?:ue)?s?\s*[:=]?\s*(\d+)\s*(?:[:,\-]|to)\s*(\d+)\b",
        r"\bresidue\s+range\s*[:=]?\s*(\d+)\s*(?:[:,\-]|to)\s*(\d+)\b",
        r"\bresidues?\s+(\d+)\s*(?:through|thru|to|-)\s*(\d+)\b",
        r"\bresid(?:ue)?s?\s+(\d+)\s+to\s+(\d+)\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            if start > end:
                start, end = end, start
            return start, end
    return None


def extract_residue_range_for_domain(
    text: str,
    domain_label: Optional[str],
) -> Optional[Tuple[int, int]]:
    """
    Extract residue range scoped near the requested domain phrase.

    Avoids picking up unrelated analysis ranges (e.g. activation-loop RMSF
    resid 150-190 when the simulation target is the kinase domain).
    """
    if not text or not domain_label:
        return None

    phrase = domain_label.replace("_", " ")
    match = re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE)
    if not match:
        return None

    # Window around the domain mention — stop before analysis-only clauses
    window_start = max(0, match.start() - 80)
    window_end = min(len(text), match.end() + 200)
    window = text[window_start:window_end]
    sim_parts = re.split(
        r"\b(?:for\s+analysis|during\s+analysis|analysis\s+compute|analysis:|"
        r"RMSF|DCCM|DSSP|overlay\s+plot|compare\s+dynamics|per-residue)\b",
        window,
        maxsplit=1,
        flags=re.IGNORECASE,
    )
    sim_window = sim_parts[0]

    patterns = [
        r"\bresid(?:ue)?s?\s*[:=]?\s*(\d+)\s*(?:[:,\-]|to)\s*(\d+)\b",
        r"\bresidue\s+range\s*[:=]?\s*(\d+)\s*(?:[:,\-]|to)\s*(\d+)\b",
        r"\bresidues?\s+(\d+)\s*(?:through|thru|to|-)\s*(\d+)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, sim_window, re.IGNORECASE)
        if m:
            start, end = int(m.group(1)), int(m.group(2))
            if start > end:
                start, end = end, start
            return start, end
    return None


def resolve_domain_residue_range(
    uniprot_id: str,
    domain_label: str,
    explicit_range: Optional[Tuple[int, int]] = None,
) -> Dict[str, Any]:
    """
    Resolve residue boundaries: explicit user range > UniProt > offline fallback.
    """
    if explicit_range:
        return {
            "start_resid": explicit_range[0],
            "end_resid": explicit_range[1],
            "residue_range": f"{explicit_range[0]}-{explicit_range[1]}",
            "domain_lookup_source": "user_specified",
            "domain_lookup_description": "Residue range from user prompt",
            "domain_lookup_success": True,
        }

    lookup = lookup_domain_range(uniprot_id, domain_label)
    if lookup and lookup.get("start_resid") and lookup.get("end_resid"):
        return {
            "start_resid": lookup["start_resid"],
            "end_resid": lookup["end_resid"],
            "residue_range": f"{lookup['start_resid']}-{lookup['end_resid']}",
            "domain_lookup_source": lookup.get("source", "unknown"),
            "domain_lookup_description": lookup.get("description", ""),
            "domain_lookup_success": True,
            "domain_lookup_message": lookup.get("message", ""),
            "domain_lookup_details": lookup,
        }

    return {
        "domain_lookup_success": False,
        "domain_lookup_error": (lookup or {}).get("error", "Domain lookup failed"),
        "domain_lookup_details": lookup,
    }


def extract_structure_source(text: str) -> str:
    """Infer preferred download source from goal text."""
    if not text:
        return "auto"
    lower = text.lower()
    if "alphafold" in lower:
        return "alphafold"
    if "rcsb" in lower or "protein data bank" in lower or "pdb bank" in lower:
        return "rcsb"
    return "auto"


def parse_structure_request(text: str) -> Optional[Dict[str, Any]]:
    """
    Parse a structure acquisition request from user goal / planner instructions.

    Returns None if no UniProt ID is found.
    """
    if not text:
        return None

    uniprot_ids = extract_uniprot_ids(text)
    if not uniprot_ids:
        return None

    uniprot_id = uniprot_ids[0]
    protein_name = extract_protein_name(text, uniprot_id)
    domain_label = extract_domain_label(text)

    # Scope explicit ranges to the simulation domain when possible
    if domain_label:
        residue_range = extract_residue_range_for_domain(text, domain_label)
    else:
        residue_range = extract_residue_range(text)

    domain_lookup: Dict[str, Any] = {}
    if domain_label and not residue_range:
        domain_lookup = resolve_domain_residue_range(uniprot_id, domain_label)
        if domain_lookup.get("domain_lookup_success"):
            residue_range = (
                domain_lookup["start_resid"],
                domain_lookup["end_resid"],
            )

    needs_download = not re.search(r"\b[\w\-]+\.pdb\b", text, re.IGNORECASE) or bool(
        re.search(r"\bdownload\b", text, re.IGNORECASE)
    )

    result = {
        "uniprot_id": uniprot_id,
        "protein_name": protein_name,
        "domain_label": domain_label,
        "residue_range": residue_range,
        "start_resid": residue_range[0] if residue_range else None,
        "end_resid": residue_range[1] if residue_range else None,
        "needs_download": needs_download,
        "extract_domain": bool(residue_range or domain_label),
        "structure_source": extract_structure_source(text),
    }
    if domain_lookup:
        result.update(domain_lookup)
    return result


def build_domain_context_for_agents(request: Dict[str, Any]) -> str:
    """Human-readable domain annotation block for planner/agent prompts."""
    if not request or not request.get("domain_label"):
        return ""

    lines = [
        f"**Domain target:** {request['domain_label'].replace('_', ' ')}",
        f"**UniProt:** {request.get('uniprot_id', 'unknown')}",
    ]
    if request.get("protein_name"):
        lines.append(f"**Protein:** {request['protein_name']}")

    if request.get("start_resid") and request.get("end_resid"):
        source = request.get("domain_lookup_source", "unknown")
        desc = request.get("domain_lookup_description", "")
        lines.append(
            f"**Residue range (UniProt numbering):** "
            f"{request['start_resid']}-{request['end_resid']} "
            f"(source: {source})"
        )
        if desc:
            lines.append(f"**Annotation:** {desc}")
        lines.append(
            "**Action:** extract_domain on downloaded/full PDB before preprocessing "
            f"→ output e.g. {build_output_basename(request)}.pdb"
        )
    elif request.get("domain_label"):
        lines.append(
            "**Warning:** domain requested but residue range could not be resolved. "
            "Run lookup_domain_range_tool or provide explicit resid range."
        )
    return "\n".join(lines)


def build_output_basename(request: Dict[str, Any]) -> str:
    """Build output filename stem, e.g. ERBB3_kinase_domain."""
    name = request.get("protein_name") or request.get("uniprot_id", "protein")
    domain = request.get("domain_label")
    if domain:
        return f"{name}_{domain}"
    if request.get("extract_domain"):
        return f"{name}_domain"
    return str(name)
