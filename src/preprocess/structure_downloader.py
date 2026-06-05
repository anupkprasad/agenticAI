"""
Structure download tool — fetches PDB coordinates from modular sources.
"""
import os
from typing import Dict, Any, Optional, List

from langchain.tools import tool

from .structure_sources import download_structure as _download, list_structure_sources


@tool
def download_structure(
    uniprot_id: str,
    output_file: Optional[str] = None,
    source: str = "auto",
    source_order: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Download a protein structure for a UniProt accession from AlphaFold DB,
    RCSB PDB, or other registered sources.

    Use when the user requests simulation of a protein/domain but no local PDB
    file is available. Prefer source='auto' to try AlphaFold first, then RCSB.

    Args:
        uniprot_id: UniProt accession (e.g. P21860 for ERBB3)
        output_file: Output PDB filename or path (default: {uniprot_id}.pdb)
        source: 'auto', 'alphafold', or 'rcsb'
        source_order: Optional override for auto fallback order

    Returns:
        Dict with success, output_file, source used, and message/error
    """
    uid = (uniprot_id or "").strip().upper()
    if not uid:
        return {"success": False, "error": "uniprot_id is required"}

    out = output_file or f"{uid.lower()}.pdb"
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)

    result = _download(
        uniprot_id=uid,
        output_path=out,
        source=source,
        source_order=source_order,
    )
    if result.get("success"):
        result.setdefault("output_file", out)
        result.setdefault(
            "available_sources",
            [s["name"] for s in list_structure_sources()],
        )
    return result
