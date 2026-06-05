"""
LangChain tool for looking up domain residue ranges from UniProt and fallbacks.
"""
from typing import Dict, Any, Optional, List

from langchain.tools import tool

from .domain_sources import lookup_domain_range, list_domain_sources


@tool
def lookup_domain_range_tool(
    uniprot_id: str,
    domain_label: str = "kinase_domain",
    source_order: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Look up UniProt residue boundaries for a protein domain.

    Use when the user requests simulation of a domain (e.g. kinase domain)
    but does not provide explicit residue numbers. Queries UniProt feature
    annotations first, then curated offline fallbacks.

    Example: lookup_domain_range_tool("P21860", "kinase_domain")
    → Protein kinase domain residues 709-966 (UniProt annotation)

    Args:
        uniprot_id: UniProt accession (e.g. P21860 for ERBB3)
        domain_label: Domain name (kinase_domain, activation_loop, sh2_domain, etc.)
        source_order: Optional source priority (default: uniprot, offline)

    Returns:
        Dict with start_resid, end_resid, source, description, and message
    """
    result = lookup_domain_range(
        uniprot_id=uniprot_id.strip().upper(),
        domain_label=domain_label,
        source_order=source_order,
    )
    if not result:
        return {
            "success": False,
            "error": "lookup_domain_range returned no result",
        }
    if result.get("start_resid") and result.get("end_resid"):
        result.setdefault("success", True)
        result.setdefault(
            "residue_range",
            f"{result['start_resid']}-{result['end_resid']}",
        )
    return result
