"""Modular protein structure download sources."""

from .registry import (
    download_structure,
    get_structure_source,
    list_structure_sources,
    DEFAULT_SOURCE_ORDER,
)
from .base import StructureSource
from .alphafold import AlphaFoldSource
from .rcsb import RCSBSource

__all__ = [
    "StructureSource",
    "AlphaFoldSource",
    "RCSBSource",
    "download_structure",
    "get_structure_source",
    "list_structure_sources",
    "DEFAULT_SOURCE_ORDER",
]
