"""
LangChain tools for structure remodeling: merge missing residues/atoms from
AlphaFold (or other model) structures into experimental PDB files.
"""
import os
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np

from langchain.tools import tool

from .aligner import auto_align_chains, superpose_structures
from .gap_detector import detect_structure_gaps
from .residue_transfer import (
    anchor_pairs_excluding_donor_resids,
    donor_resids_from_range,
    remodel_merge,
)
from .sequence_utils import (
    align_chain_sequences,
    extract_chain_sequences,
    flanking_residue_pairs,
    pick_default_chain,
)


def _default_output(target_pdb: str, suffix: str = "remodeled") -> str:
    path = Path(target_pdb)
    return str(path.parent / f"{path.stem}_{suffix}.pdb")


@tool
def detect_missing_structure_elements(
    target_pdb: str,
    donor_pdb: str,
    target_chain: Optional[str] = None,
    donor_chain: Optional[str] = None,
    check_atoms: bool = True,
) -> Dict[str, Any]:
    """
    Align experimental and model structures by sequence and report gaps.

    Compares target (experimental) vs donor (e.g. AlphaFold) PDB files to find
    missing residues and heavy atoms (including phosphate groups on SEP/TPO/PTR).

    Args:
        target_pdb: Experimental / target PDB file path
        donor_pdb: Model PDB file path (e.g. AlphaFold AF3)
        target_chain: Target chain ID (optional; longest chain if omitted)
        donor_chain: Donor chain ID (optional; longest chain if omitted)
        check_atoms: Whether to scan aligned residues for missing atoms

    Returns:
        Dict with missing residue ranges, per-residue missing atoms, alignment score
    """
    if not os.path.isfile(target_pdb):
        return {"success": False, "error": f"Target PDB not found: {target_pdb}"}
    if not os.path.isfile(donor_pdb):
        return {"success": False, "error": f"Donor PDB not found: {donor_pdb}"}

    try:
        report = detect_structure_gaps(
            target_pdb,
            donor_pdb,
            target_chain=target_chain,
            donor_chain=donor_chain,
            check_atoms=check_atoms,
        )
        missing_atom_details = [
            {
                "chain": m.chain_id,
                "resid": m.resid,
                "resname": m.resname,
                "missing_atoms": m.atom_names,
                "donor_resid": m.donor_resid,
                "donor_resname": m.donor_resname,
            }
            for m in report.missing_atoms
        ]
        return {
            "success": True,
            "target_chain": report.target_chain,
            "donor_chain": report.donor_chain,
            "alignment_score": report.alignment_score,
            "aligned_pairs": report.aligned_pair_count,
            "missing_residue_resids": report.missing_residue_resids,
            "missing_residue_ranges": report.missing_residue_ranges,
            "missing_atoms": missing_atom_details,
            "missing_atom_residue_count": len(missing_atom_details),
            "message": (
                f"Missing residues: {report.missing_residue_ranges or 'none'}; "
                f"missing atoms in {len(missing_atom_details)} residues"
            ),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@tool
def remodel_structure(
    target_pdb: str,
    donor_pdb: str,
    output_file: Optional[str] = None,
    target_chain: Optional[str] = None,
    donor_chain: Optional[str] = None,
    mode: str = "auto",
    donor_residue_range: Optional[str] = None,
    copy_missing_residues: bool = True,
    copy_missing_atoms: bool = True,
) -> Dict[str, Any]:
    """
    Remodel experimental PDB by copying missing residues/atoms from a model structure.

    Superposes donor onto target, then merges only missing content (does not replace
    existing experimental coordinates). Supports manual residue ranges (e.g. copy
    AF3 residues 165-168) or automatic gap detection via sequence alignment.

    Args:
        target_pdb: Experimental structure to update
        donor_pdb: Model structure (AlphaFold / AF3) as coordinate donor
        output_file: Output PDB path (default: {target}_remodeled.pdb)
        target_chain: Chain ID on target (optional)
        donor_chain: Chain ID on donor (optional)
        mode: 'auto' (detect gaps) or 'manual' (requires donor_residue_range)
        donor_residue_range: Manual donor resids to copy, e.g. '165-168' or '165,166'
        copy_missing_residues: Insert full missing residues from donor
        copy_missing_atoms: Add missing heavy atoms (e.g. phosphate) to existing residues

    Returns:
        Dict with output_file, superposition RMSD, copied residues, added atoms
    """
    if not os.path.isfile(target_pdb):
        return {"success": False, "error": f"Target PDB not found: {target_pdb}"}
    if not os.path.isfile(donor_pdb):
        return {"success": False, "error": f"Donor PDB not found: {donor_pdb}"}

    if mode not in {"auto", "manual"}:
        return {"success": False, "error": f"Invalid mode: {mode}. Use 'auto' or 'manual'."}

    if mode == "manual" and not donor_residue_range:
        return {
            "success": False,
            "error": "manual mode requires donor_residue_range (e.g. '165-168')",
        }

    out = output_file or _default_output(target_pdb)

    try:
        target_chains = extract_chain_sequences(target_pdb, target_chain)
        donor_chains = extract_chain_sequences(donor_pdb, donor_chain)
        t_id = target_chain or pick_default_chain(target_chains)
        d_id = donor_chain or pick_default_chain(donor_chains)

        alignment = align_chain_sequences(
            target_chains[t_id],
            donor_chains[d_id],
        )

        manual_resids: set = set()
        if mode == "manual":
            manual_resids = set(
                donor_resids_from_range(donor_pdb, d_id, donor_residue_range)
            )

        if mode == "manual":
            anchor_pairs = flanking_residue_pairs(
                target_chains[t_id],
                donor_chains[d_id],
                sorted(manual_resids),
            )
            if len(anchor_pairs) < 2:
                extra = anchor_pairs_excluding_donor_resids(
                    alignment.aligned_pairs,
                    manual_resids,
                )
                seen = {(p.target_resid, p.donor_resid) for p in anchor_pairs}
                for pair in extra:
                    key = (pair.target_resid, pair.donor_resid)
                    if key not in seen:
                        anchor_pairs.append(pair)
                        seen.add(key)
            exclude_for_fit = manual_resids
        else:
            anchor_pairs = alignment.aligned_pairs
            exclude_for_fit = set()

        sup = superpose_structures(
            target_pdb,
            donor_pdb,
            t_id,
            d_id,
            anchor_pairs=anchor_pairs if anchor_pairs else alignment.aligned_pairs,
            exclude_donor_resids=exclude_for_fit,
        )

        gap_report = detect_structure_gaps(
            target_pdb,
            donor_pdb,
            target_chain=t_id,
            donor_chain=d_id,
            check_atoms=copy_missing_atoms,
        )

        if mode == "manual":
            donor_resids_to_copy = sorted(manual_resids) if copy_missing_residues else []
            missing_atoms = gap_report.missing_atoms if copy_missing_atoms else []
        else:
            donor_resids_to_copy = (
                gap_report.missing_residue_resids if copy_missing_residues else []
            )
            missing_atoms = gap_report.missing_atoms if copy_missing_atoms else []

        merge_result = remodel_merge(
            target_pdb,
            donor_pdb,
            out,
            t_id,
            d_id,
            sup,
            donor_resids_to_copy,
            missing_atoms,
            copy_residues=copy_missing_residues and bool(donor_resids_to_copy),
            copy_atoms=copy_missing_atoms and bool(missing_atoms),
        )

        return {
            "success": True,
            "output_file": out,
            "mode": mode,
            "target_chain": t_id,
            "donor_chain": d_id,
            "superposition_rmsd": sup.rmsd,
            "superposition_pairs": sup.atom_pairs,
            "copied_residue_resids": merge_result.get("residue_copy", {}).get(
                "copied_residue_resids", []
            ),
            "added_atom_count": merge_result.get("atom_copy", {}).get(
                "added_atom_count", 0
            ),
            "missing_residue_ranges_detected": gap_report.missing_residue_ranges,
            "log": merge_result.get("log", []),
            "message": (
                f"Remodeled structure written to {out} "
                f"(RMSD {sup.rmsd:.2f} Å over {sup.atom_pairs} CA pairs)"
            ),
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@tool
def align_model_to_experimental(
    target_pdb: str,
    donor_pdb: str,
    output_file: Optional[str] = None,
    target_chain: Optional[str] = None,
    donor_chain: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Superpose donor structure onto experimental target and write aligned donor PDB.

    Useful for visual inspection before merging. Does not modify the target file.

    Args:
        target_pdb: Experimental reference structure
        donor_pdb: Model structure to align
        output_file: Aligned donor output path (default: {donor}_aligned.pdb)
        target_chain: Target chain ID (optional)
        donor_chain: Donor chain ID (optional)

    Returns:
        Dict with RMSD, output path, and chain IDs used
    """
    if not os.path.isfile(target_pdb):
        return {"success": False, "error": f"Target PDB not found: {target_pdb}"}
    if not os.path.isfile(donor_pdb):
        return {"success": False, "error": f"Donor PDB not found: {donor_pdb}"}

    out = output_file or _default_output(donor_pdb, "aligned")

    try:
        from Bio.PDB import PDBIO, PDBParser

        from .aligner import transform_coordinates

        t_id, d_id, sup = auto_align_chains(
            target_pdb, donor_pdb, target_chain, donor_chain,
        )

        parser = PDBParser(QUIET=True)
        donor_struct = parser.get_structure("donor", donor_pdb)
        for atom in donor_struct.get_atoms():
            atom.coord = transform_coordinates(
                np.array(atom.coord).reshape(1, 3),
                sup.rotation,
                sup.translation,
            )[0]

        io = PDBIO()
        io.set_structure(donor_struct)
        io.save(out)

        return {
            "success": True,
            "output_file": out,
            "target_chain": t_id,
            "donor_chain": d_id,
            "superposition_rmsd": sup.rmsd,
            "superposition_pairs": sup.atom_pairs,
            "message": f"Aligned donor written to {out} (RMSD {sup.rmsd:.2f} Å)",
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
