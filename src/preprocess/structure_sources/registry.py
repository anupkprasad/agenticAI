"""
Registry of structure download sources with fallback ordering.
"""
from typing import Dict, List, Optional, Any

from .base import StructureSource
from .alphafold import AlphaFoldSource
from .rcsb import RCSBSource


DEFAULT_SOURCE_ORDER = ("alphafold", "rcsb")

_SOURCES: Dict[str, StructureSource] = {
    "alphafold": AlphaFoldSource(),
    "rcsb": RCSBSource(),
}


def get_structure_source(name: str) -> Optional[StructureSource]:
    """Return a registered source by name."""
    return _SOURCES.get(name.lower())


def list_structure_sources() -> List[Dict[str, str]]:
    """List available sources for documentation / LLM prompts."""
    return [
        {"name": src.name, "description": src.description}
        for src in _SOURCES.values()
    ]


def download_structure(
    uniprot_id: str,
    output_path: str,
    source: str = "auto",
    source_order: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Download a structure using a specific source or fallback chain.

    Args:
        uniprot_id: UniProt accession (e.g. P21860)
        output_path: Destination PDB path
        source: Source name or "auto" for ordered fallback
        source_order: Override default fallback order
    """
    if source and source.lower() != "auto":
        src = get_structure_source(source)
        if not src:
            return {
                "success": False,
                "error": f"Unknown structure source: {source}",
                "available_sources": list(_SOURCES.keys()),
            }
        return src.download(uniprot_id, output_path)

    order = source_order or list(DEFAULT_SOURCE_ORDER)
    attempts = []
    for name in order:
        src = get_structure_source(name)
        if not src or not src.can_fetch(uniprot_id):
            continue
        result = src.download(uniprot_id, output_path)
        attempts.append({"source": name, "success": result.get("success"), "error": result.get("error")})
        if result.get("success"):
            result["attempts"] = attempts
            return result

    return {
        "success": False,
        "error": f"All structure sources failed for UniProt {uniprot_id}",
        "attempts": attempts,
        "available_sources": list(_SOURCES.keys()),
    }
