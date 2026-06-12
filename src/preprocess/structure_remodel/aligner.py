"""
Structural superposition between target and donor PDB files.
"""
from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np

from .sequence_utils import ResiduePair, align_chain_sequences, extract_chain_sequences, pick_default_chain


@dataclass
class SuperpositionResult:
    rotation: np.ndarray
    translation: np.ndarray
    rmsd: float
    atom_pairs: int


def _get_ca_position(pdb_file: str, chain_id: str, resid: int) -> Optional[np.ndarray]:
    import MDAnalysis as mda

    u = mda.Universe(pdb_file)
    sel = u.select_atoms(
        f"protein and name CA and chainID {chain_id} and resid {resid}"
    )
    if len(sel) == 0:
        return None
    return sel.positions[0].copy()


def superpose_structures(
    target_pdb: str,
    donor_pdb: str,
    target_chain: str,
    donor_chain: str,
    anchor_pairs: Optional[List[ResiduePair]] = None,
    exclude_donor_resids: Optional[set] = None,
) -> SuperpositionResult:
    """
    Compute rotation/translation to superpose donor onto target using CA atoms.

    Args:
        anchor_pairs: Explicit residue pairs for fitting; auto-aligned when omitted.
        exclude_donor_resids: Donor resids excluded from fitting (e.g. insert region).
    """
    if anchor_pairs is None:
        target_chains = extract_chain_sequences(target_pdb, target_chain)
        donor_chains = extract_chain_sequences(donor_pdb, donor_chain)
        alignment = align_chain_sequences(
            target_chains[target_chain],
            donor_chains[donor_chain],
        )
        anchor_pairs = alignment.aligned_pairs

    exclude = exclude_donor_resids or set()
    ref_coords: List[np.ndarray] = []
    mobile_coords: List[np.ndarray] = []

    for pair in anchor_pairs:
        if pair.donor_resid in exclude:
            continue
        ref = _get_ca_position(target_pdb, target_chain, pair.target_resid)
        mobile = _get_ca_position(donor_pdb, donor_chain, pair.donor_resid)
        if ref is not None and mobile is not None:
            ref_coords.append(ref)
            mobile_coords.append(mobile)

    if len(ref_coords) < 2:
        raise ValueError(
            f"Need at least 2 CA pairs for superposition; found {len(ref_coords)}"
        )

    ref_arr = np.array(ref_coords)
    mobile_arr = np.array(mobile_coords)

    rot, translation, rmsd = _kabsch_fit(mobile_arr, ref_arr)

    return SuperpositionResult(
        rotation=rot,
        translation=translation,
        rmsd=float(rmsd),
        atom_pairs=len(ref_coords),
    )


def _kabsch_fit(
    mobile: np.ndarray,
    ref: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray, float]:
    """
    Kabsch alignment: transform mobile coordinates onto ref.

    Returns (rotation, translation, RMSD) where mobile @ rot.T + translation ≈ ref.
    """
    mobile_cent = mobile.mean(axis=0)
    ref_cent = ref.mean(axis=0)
    mobile_rel = mobile - mobile_cent
    ref_rel = ref - ref_cent

    cov = mobile_rel.T @ ref_rel
    v, _s, wt = np.linalg.svd(cov)
    d = np.sign(np.linalg.det(v @ wt))
    diag = np.diag([1.0, 1.0, d])
    rot = v @ diag @ wt

    translation = ref_cent - mobile_cent @ rot.T
    fitted = mobile @ rot.T + translation
    rmsd = float(np.sqrt(np.mean(np.sum((fitted - ref) ** 2, axis=1))))

    return rot, translation, rmsd


def transform_coordinates(
    coords: np.ndarray,
    rotation: np.ndarray,
    translation: np.ndarray,
) -> np.ndarray:
    """Apply rotation and translation to Nx3 coordinates."""
    return coords @ rotation.T + translation


def auto_align_chains(
    target_pdb: str,
    donor_pdb: str,
    target_chain: Optional[str] = None,
    donor_chain: Optional[str] = None,
    exclude_donor_resids: Optional[set] = None,
) -> Tuple[str, str, SuperpositionResult]:
    """Pick chains, align sequences, and superpose structures."""
    target_chains = extract_chain_sequences(target_pdb, target_chain)
    donor_chains = extract_chain_sequences(donor_pdb, donor_chain)
    t_id = target_chain or pick_default_chain(target_chains)
    d_id = donor_chain or pick_default_chain(donor_chains)

    sup = superpose_structures(
        target_pdb,
        donor_pdb,
        t_id,
        d_id,
        exclude_donor_resids=exclude_donor_resids,
    )
    return t_id, d_id, sup
