"""
Abstract base for modular domain annotation sources (UniProt, InterPro, etc.).
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class DomainSource(ABC):
    """Base class for domain/residue-range lookup adapters."""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def lookup(
        self,
        uniprot_id: str,
        domain_label: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Return domain metadata dict or None if not found.

        Expected keys: start_resid, end_resid, description, source, confidence
        """
