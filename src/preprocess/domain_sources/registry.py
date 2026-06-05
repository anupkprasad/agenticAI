"""
Registry for domain boundary lookup with source fallback.
"""
from typing import Any, Dict, List, Optional, Tuple

from .base import DomainSource
from .uniprot import UniProtDomainSource

# Offline fallback when APIs are unavailable (UniProt numbering)
OFFLINE_DOMAIN_RANGES: Dict[str, Dict[str, Tuple[int, int]]] = {
    "P21860": {"kinase_domain": (709, 966), "kinase": (709, 966)},
    "P00533": {"kinase_domain": (712, 979), "kinase": (712, 979)},
    "Q9Y2H2": {"kinase_domain": (703, 966), "kinase": (703, 966)},
}

DEFAULT_SOURCE_ORDER = ("uniprot", "offline")

_SOURCES: Dict[str, DomainSource] = {
    "uniprot": UniProtDomainSource(),
}


def list_domain_sources() -> List[Dict[str, str]]:
    return [
        {"name": "uniprot", "description": UniProtDomainSource.description},
        {"name": "offline", "description": "Curated fallback ranges"},
    ]


def _offline_lookup(uniprot_id: str, domain_label: str) -> Optional[Dict[str, Any]]:
    uid = uniprot_id.strip().upper()
    key = domain_label.lower().replace(" ", "_")
    ranges = OFFLINE_DOMAIN_RANGES.get(uid, {})

    for candidate in (key, "kinase_domain", "kinase"):
        if candidate in ranges:
            start, end = ranges[candidate]
            return {
                "success": True,
                "source": "offline",
                "uniprot_id": uid,
                "domain_label": domain_label,
                "start_resid": start,
                "end_resid": end,
                "description": f"Curated {candidate}",
                "confidence": "curated",
                "message": f"Offline curated {candidate}: {start}-{end}",
            }
    return None


def lookup_domain_range(
    uniprot_id: str,
    domain_label: str,
    source_order: Optional[List[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Resolve domain residue boundaries for a UniProt accession.

    Tries UniProt REST API first, then offline curated ranges.
    """
    if not uniprot_id or not domain_label:
        return None

    order = source_order or list(DEFAULT_SOURCE_ORDER)
    attempts = []

    for name in order:
        if name == "offline":
            result = _offline_lookup(uniprot_id, domain_label)
            attempts.append({"source": name, "found": bool(result)})
            if result:
                result["attempts"] = attempts
                return result
            continue

        src = _SOURCES.get(name)
        if not src:
            continue
        result = src.lookup(uniprot_id, domain_label)
        attempts.append(
            {
                "source": name,
                "found": bool(result and result.get("start_resid")),
                "error": (result or {}).get("error"),
            }
        )
        if result and result.get("start_resid") and result.get("end_resid"):
            result["attempts"] = attempts
            return result

    return {
        "success": False,
        "uniprot_id": uniprot_id,
        "domain_label": domain_label,
        "error": f"No domain range found for {domain_label} on {uniprot_id}",
        "attempts": attempts,
    }
