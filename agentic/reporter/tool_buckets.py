"""Reporter tool scope buckets: per_sim / combined / shared."""
from __future__ import annotations

from typing import Dict, FrozenSet, List

PER_SIM_TOOL_NAMES: FrozenSet[str] = frozenset({
    "read_analysis_summary",
    "generate_html_report",
})

COMBINED_TOOL_NAMES: FrozenSet[str] = frozenset({
    "generate_combined_html_report",
})

SHARED_TOOL_NAMES: FrozenSet[str] = frozenset({
    "search_pubmed",
    "search_biorxiv",
    "search_uniprot",
    "generate_literature_queries",
})


def summarize_buckets() -> Dict[str, List[str]]:
    return {
        "per_sim": sorted(PER_SIM_TOOL_NAMES),
        "combined": sorted(COMBINED_TOOL_NAMES),
        "shared": sorted(SHARED_TOOL_NAMES),
    }
