"""Modular domain boundary lookup sources."""

from .registry import lookup_domain_range, list_domain_sources, OFFLINE_DOMAIN_RANGES
from .uniprot import UniProtDomainSource, DOMAIN_KEYWORDS

__all__ = [
    "lookup_domain_range",
    "list_domain_sources",
    "OFFLINE_DOMAIN_RANGES",
    "UniProtDomainSource",
    "DOMAIN_KEYWORDS",
]
