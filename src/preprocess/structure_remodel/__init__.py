"""
Structure remodeling: merge missing residues/atoms from model PDB into experimental PDB.
"""

from .gap_detector import detect_structure_gaps, StructureGapReport
from .remodel_tool import (
    align_model_to_experimental,
    detect_missing_structure_elements,
    remodel_structure,
)
from .sequence_utils import extract_chain_sequences, parse_residue_range

__all__ = [
    "detect_structure_gaps",
    "StructureGapReport",
    "align_model_to_experimental",
    "detect_missing_structure_elements",
    "remodel_structure",
    "extract_chain_sequences",
    "parse_residue_range",
]
