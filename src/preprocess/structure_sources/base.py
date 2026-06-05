"""
Abstract base for modular protein structure download sources.

Each source implements download() and can_fetch() so the registry can
try sources in priority order or let the user pick a specific database.
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class StructureSource(ABC):
    """Base class for structure database adapters."""

    name: str = "base"
    description: str = ""

    @abstractmethod
    def can_fetch(self, uniprot_id: str) -> bool:
        """Return True if this source can attempt a fetch for the UniProt ID."""

    @abstractmethod
    def download(self, uniprot_id: str, output_path: str) -> Dict[str, Any]:
        """
        Download a structure for the UniProt ID to output_path.

        Returns dict with at least: success (bool), source, message/error.
        """
