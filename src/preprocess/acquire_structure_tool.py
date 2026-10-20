"""
LangChain tool wrapper for automated structure acquisition pipeline.
"""
from typing import Dict, Any, Optional

from langchain.tools import tool

from .structure_acquisition import acquire_structure_from_request


@tool
def acquire_protein_structure(
    user_request: str,
    output_dir: str = ".",
    source: str = "auto",
) -> Dict[str, Any]:
    """
    Download and prepare a protein structure when no PDB file is provided.

    Parses UniProt ID or RCSB PDB ID, optional protein name / domain / residue
    range from the user request. UniProt IDs download from AlphaFold (RCSB
    fallback) with optional domain trim; bare PDB IDs (e.g. 6VC0) download
    directly from RCSB.

    Example request text:
    "Simulate kinase domain of UniProt P21860 (ERBB3), residues 503-771"
    "Download PDB 6VC0 and prepare for MD"

    Args:
        user_request: Natural language description with UniProt / domain info
        output_dir: Directory for downloaded and trimmed PDB files
        source: 'auto', 'alphafold', or 'rcsb'

    Returns:
        Dict with success, pdb_file path, validation results, and step log
    """
    return acquire_structure_from_request(
        text=user_request,
        working_dir=output_dir,
        source=source,
    )
