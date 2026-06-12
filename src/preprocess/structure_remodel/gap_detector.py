"""
Detect missing residues and atoms between experimental and model structures.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .sequence_utils import (
    ChainSequence,
    SequenceAlignmentResult,
    align_chain_sequences,
    extract_chain_sequences,
    format_gaps,
    pick_default_chain,
)


# Standard heavy atoms expected per residue (backbone + sidechain, no H)
BACKBONE_ATOMS = {"N", "CA", "C", "O"}
SIDECHAIN_ATOMS: Dict[str, Set[str]] = {
    "ALA": {"CB"},
    "CYS": {"CB", "SG"},
    "ASP": {"CB", "CG", "OD1", "OD2"},
    "GLU": {"CB", "CG", "CD", "OE1", "OE2"},
    "PHE": {"CB", "CG", "CD1", "CD2", "CE1", "CE2", "CZ"},
    "GLY": set(),
    "HIS": {"CB", "CG", "ND1", "CD2", "CE1", "NE2"},
    "ILE": {"CB", "CG1", "CG2", "CD1"},
    "LEU": {"CB", "CG", "CD1", "CD2"},
    "LYS": {"CB", "CG", "CD", "CE", "NZ"},
    "MET": {"CB", "CG", "SD", "CE"},
    "ASN": {"CB", "CG", "OD1", "ND2"},
    "PRO": {"CB", "CG", "CD"},
    "GLN": {"CB", "CG", "CD", "OE1", "NE2"},
    "ARG": {"CB", "CG", "CD", "NE", "CZ", "NH1", "NH2"},
    "SER": {"CB", "OG"},
    "THR": {"CB", "OG1", "CG2"},
    "VAL": {"CB", "CG1", "CG2"},
    "TRP": {"CB", "CG", "CD1", "CD2", "NE1", "CE2", "CE3", "CZ2", "CZ3", "CH2"},
    "TYR": {"CB", "CG", "CD1", "CD2", "CE1", "CE2", "CZ", "OH"},
    # Phosphorylated residues in models
    "SEP": {"CB", "OG", "P", "O1P", "O2P", "O3P"},
    "TPO": {"CB", "OG1", "CG2", "P", "O1P", "O2P", "O3P"},
    "PTR": {"CB", "CG", "CD1", "CD2", "CE1", "CE2", "CZ", "OH", "P", "O1P", "O2P", "O3P"},
    "TP2": {"CB", "CG", "CD1", "CD2", "CE1", "CE2", "CZ", "OH", "P", "O1P", "O2P", "OT"},
}


@dataclass
class MissingAtom:
    chain_id: str
    resid: int
    resname: str
    atom_names: List[str]
    donor_resid: int
    donor_resname: str


@dataclass
class StructureGapReport:
    target_pdb: str
    donor_pdb: str
    target_chain: str
    donor_chain: str
    alignment_score: float
    missing_residue_resids: List[int]
    missing_residue_ranges: str
    missing_atoms: List[MissingAtom]
    aligned_pair_count: int


def _residue_atom_names(pdb_file: str, chain_id: str, resid: int) -> Set[str]:
    import MDAnalysis as mda

    u = mda.Universe(pdb_file)
    sel = u.select_atoms(
        f"protein and chainID {chain_id} and resid {resid}"
    )
    return {a.name.strip() for a in sel.atoms}


def _expected_atoms(resname: str, observed: Set[str]) -> Set[str]:
    """Expected heavy atoms: standard set union any observed non-H atoms."""
    base = BACKBONE_ATOMS | SIDECHAIN_ATOMS.get(resname.upper(), set())
    for name in observed:
        if not name.startswith("H"):
            base.add(name)
    return base


def missing_resids_by_numbering(chain: ChainSequence) -> List[int]:
    """Residue numbers absent between the first and last observed CA in a chain."""
    if not chain.resids:
        return []
    expected = set(range(chain.resids[0], chain.resids[-1] + 1))
    return sorted(expected - set(chain.resids))


def combined_missing_donor_resids(alignment: SequenceAlignmentResult) -> List[int]:
    """
    Donor residue numbers that should be copied into the target.

    Only includes residues absent from the target (never overwrites experimental
    coordinates). Uses numbering gaps and donor resids missing from the target
    within the combined span of both structures.
    """
    target_resids = set(alignment.target_chain.resids)
    donor_resids = set(alignment.donor_chain.resids)

    from_gaps = [
        r
        for r in missing_resids_by_numbering(alignment.target_chain)
        if r in donor_resids
    ]

    if target_resids and donor_resids:
        span_start = min(min(target_resids), min(donor_resids))
        span_end = max(max(target_resids), max(donor_resids))
        span = set(range(span_start, span_end + 1))
        absent_from_target = sorted((donor_resids - target_resids) & span)
    else:
        absent_from_target = sorted(donor_resids - target_resids)

    return sorted(set(from_gaps) | set(absent_from_target))


def find_missing_atoms_for_pair(
    target_pdb: str,
    donor_pdb: str,
    target_chain: str,
    donor_chain: str,
    target_resid: int,
    donor_resid: int,
    target_resname: str,
    donor_resname: str,
) -> List[str]:
    """Return donor atom names missing from the target residue."""
    target_atoms = _residue_atom_names(target_pdb, target_chain, target_resid)
    donor_atoms = _residue_atom_names(donor_pdb, donor_chain, donor_resid)

    # Prefer donor residue name for expected atom template (handles phosphorylation)
    template_resname = donor_resname if donor_resname in SIDECHAIN_ATOMS else target_resname
    expected_donor = _expected_atoms(template_resname, donor_atoms)
    missing = sorted(expected_donor - target_atoms)
    # Only copy atoms that exist in donor
    missing = [a for a in missing if a in donor_atoms]
    return missing


def detect_structure_gaps(
    target_pdb: str,
    donor_pdb: str,
    target_chain: Optional[str] = None,
    donor_chain: Optional[str] = None,
    check_atoms: bool = True,
) -> StructureGapReport:
    """
    Align sequences and report missing residues/atoms in target vs donor.
    """
    target_chains = extract_chain_sequences(target_pdb, target_chain)
    donor_chains = extract_chain_sequences(donor_pdb, donor_chain)

    t_chain_id = target_chain or pick_default_chain(target_chains)
    d_chain_id = donor_chain or pick_default_chain(donor_chains)

    alignment = align_chain_sequences(
        target_chains[t_chain_id],
        donor_chains[d_chain_id],
    )

    missing_resids = combined_missing_donor_resids(alignment)
    missing_atoms: List[MissingAtom] = []

    if check_atoms:
        for pair in alignment.aligned_pairs:
            missing_names = find_missing_atoms_for_pair(
                target_pdb,
                donor_pdb,
                t_chain_id,
                d_chain_id,
                pair.target_resid,
                pair.donor_resid,
                pair.target_resname,
                pair.donor_resname,
            )
            if missing_names:
                missing_atoms.append(
                    MissingAtom(
                        chain_id=t_chain_id,
                        resid=pair.target_resid,
                        resname=pair.target_resname,
                        atom_names=missing_names,
                        donor_resid=pair.donor_resid,
                        donor_resname=pair.donor_resname,
                    )
                )

    return StructureGapReport(
        target_pdb=target_pdb,
        donor_pdb=donor_pdb,
        target_chain=t_chain_id,
        donor_chain=d_chain_id,
        alignment_score=alignment.score,
        missing_residue_resids=missing_resids,
        missing_residue_ranges=format_gaps(missing_resids),
        missing_atoms=missing_atoms,
        aligned_pair_count=len(alignment.aligned_pairs),
    )
