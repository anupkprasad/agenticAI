"""
Copy residues and atoms from a donor structure into a target structure.
"""
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from Bio.PDB import Atom, PDBIO, PDBParser, Residue

from .aligner import SuperpositionResult, transform_coordinates
from .gap_detector import MissingAtom
from .sequence_utils import ResiduePair, parse_residue_range


def _find_chain(structure, chain_id: str):
    for model in structure:
        for chain in model:
            cid = chain.id.strip() or chain.id
            if chain.id == chain_id or cid == chain_id:
                return chain
    raise ValueError(f"Chain {chain_id} not found in structure")


def _get_residue(chain, resid: int) -> Optional[Residue.Residue]:
    for residue in chain:
        if residue.id[0] == " " and residue.id[1] == resid:
            return residue
    return None


def _apply_transform_to_atom(atom, rotation: np.ndarray, translation: np.ndarray):
    coord = np.array(atom.coord)
    atom.coord = transform_coordinates(coord.reshape(1, 3), rotation, translation)[0]


def _clone_atom(donor_atom, serial: int, rotation: np.ndarray, translation: np.ndarray) -> Atom.Atom:
    coord = transform_coordinates(
        np.array(donor_atom.coord).reshape(1, 3), rotation, translation,
    )[0]
    element = donor_atom.element.strip() if donor_atom.element else donor_atom.name[0]
    return Atom.Atom(
        donor_atom.name,
        coord,
        donor_atom.bfactor,
        donor_atom.occupancy,
        donor_atom.altloc,
        donor_atom.fullname,
        serial,
        element=element,
    )


def _clone_residue(
    donor_residue: Residue.Residue,
    target_resid: int,
    rotation: np.ndarray,
    translation: np.ndarray,
    serial_start: int,
) -> Tuple[Residue.Residue, int]:
    """Clone donor residue with new resid and transformed coordinates."""
    res_id = (" ", target_resid, " ")
    new_res = Residue.Residue(res_id, donor_residue.resname, donor_residue.segid)
    serial = serial_start
    for donor_atom in donor_residue:
        new_res.add(_clone_atom(donor_atom, serial, rotation, translation))
        serial += 1
    return new_res, serial


def _chain_residue_list(chain) -> List[Residue.Residue]:
    return [r for r in chain if r.id[0] == " "]


def _rebuild_chain(chain, ordered_residues: List[Residue.Residue]):
    """Replace chain contents with ordered residue list."""
    for child in list(chain.child_list):
        chain.detach_child(child.id)
    for residue in ordered_residues:
        chain.add(residue)


def _merge_residue_lists(
    existing: List[Residue.Residue],
    new_residues: List[Residue.Residue],
) -> List[Residue.Residue]:
    by_resid: Dict[int, Residue.Residue] = {r.id[1]: r for r in existing}
    for residue in new_residues:
        by_resid[residue.id[1]] = residue
    return sorted(by_resid.values(), key=lambda r: r.id[1])


def _max_serial(structure) -> int:
    max_id = 0
    for atom in structure.get_atoms():
        max_id = max(max_id, atom.serial_number)
    return max_id


def _renumber_atoms(structure):
    serial = 1
    for atom in structure.get_atoms():
        atom.serial_number = serial
        serial += 1


def copy_donor_residues(
    target_pdb: str,
    donor_pdb: str,
    output_pdb: str,
    target_chain: str,
    donor_chain: str,
    donor_resids: List[int],
    superposition: SuperpositionResult,
    use_donor_resid_numbering: bool = True,
) -> Dict[str, object]:
    """
    Copy full residues from donor into target chain.

    When use_donor_resid_numbering is True, inserted residues keep donor PDB numbers.
    """
    parser = PDBParser(QUIET=True)
    target_struct = parser.get_structure("target", target_pdb)
    donor_struct = parser.get_structure("donor", donor_pdb)

    t_chain = _find_chain(target_struct, target_chain)
    d_chain = _find_chain(donor_struct, donor_chain)

    rot = superposition.rotation
    trans = superposition.translation
    serial = _max_serial(target_struct) + 1

    new_residues: List[Residue.Residue] = []
    copied: List[int] = []

    for d_resid in donor_resids:
        out_resid = d_resid if use_donor_resid_numbering else d_resid
        if _get_residue(t_chain, out_resid) is not None:
            continue
        donor_res = _get_residue(d_chain, d_resid)
        if donor_res is None:
            continue
        cloned, serial = _clone_residue(donor_res, out_resid, rot, trans, serial)
        new_residues.append(cloned)
        copied.append(d_resid)

    existing = _chain_residue_list(t_chain)
    merged = _merge_residue_lists(existing, new_residues)
    _rebuild_chain(t_chain, merged)
    _renumber_atoms(target_struct)

    io = PDBIO()
    io.set_structure(target_struct)
    io.save(output_pdb)

    return {
        "copied_residue_resids": copied,
        "output_file": output_pdb,
        "residue_count": len(copied),
    }


def add_missing_atoms(
    pdb_file: str,
    donor_pdb: str,
    output_pdb: str,
    target_chain: str,
    donor_chain: str,
    missing_atoms: List[MissingAtom],
    superposition: SuperpositionResult,
) -> Dict[str, object]:
    """Add specific missing atoms from donor into existing target residues."""
    parser = PDBParser(QUIET=True)
    target_struct = parser.get_structure("target", pdb_file)
    donor_struct = parser.get_structure("donor", donor_pdb)

    t_chain = _find_chain(target_struct, target_chain)
    d_chain = _find_chain(donor_struct, donor_chain)

    rot = superposition.rotation
    trans = superposition.translation
    serial = _max_serial(target_struct) + 1
    added_count = 0
    updated_resnames: List[Tuple[int, str]] = []

    for item in missing_atoms:
        target_res = _get_residue(t_chain, item.resid)
        donor_res = _get_residue(d_chain, item.donor_resid)
        if target_res is None or donor_res is None:
            continue

        # Upgrade resname when donor has modified residue (e.g. SEP for phospho-SER)
        if item.donor_resname != item.resname and item.donor_resname in {"SEP", "TPO", "PTR"}:
            target_res.resname = item.donor_resname
            updated_resnames.append((item.resid, item.donor_resname))

        existing_names = {a.name.strip() for a in target_res}
        donor_atom_map = {a.name.strip(): a for a in donor_res}

        for atom_name in item.atom_names:
            if atom_name in existing_names:
                continue
            donor_atom = donor_atom_map.get(atom_name)
            if donor_atom is None:
                continue
            target_res.add(_clone_atom(donor_atom, serial, rot, trans))
            serial += 1
            added_count += 1
            existing_names.add(atom_name)

    _renumber_atoms(target_struct)
    io = PDBIO()
    io.set_structure(target_struct)
    io.save(output_pdb)

    return {
        "added_atom_count": added_count,
        "updated_resnames": updated_resnames,
        "output_file": output_pdb,
    }


def remodel_merge(
    target_pdb: str,
    donor_pdb: str,
    output_pdb: str,
    target_chain: str,
    donor_chain: str,
    superposition: SuperpositionResult,
    donor_resids_to_copy: List[int],
    missing_atoms: List[MissingAtom],
    copy_residues: bool = True,
    copy_atoms: bool = True,
) -> Dict[str, object]:
    """
    Full merge pipeline: copy missing residues then patch missing atoms.
    """
    working_target = target_pdb
    log: List[str] = []
    residue_result: Dict[str, object] = {}
    atom_result: Dict[str, object] = {}

    if copy_residues and donor_resids_to_copy:
        residue_result = copy_donor_residues(
            working_target,
            donor_pdb,
            output_pdb,
            target_chain,
            donor_chain,
            donor_resids_to_copy,
            superposition,
        )
        working_target = output_pdb
        log.append(
            f"Copied {len(residue_result.get('copied_residue_resids', []))} residues "
            f"from donor: {residue_result.get('copied_residue_resids')}"
        )

    if copy_atoms and missing_atoms:
        atom_result = add_missing_atoms(
            working_target,
            donor_pdb,
            output_pdb,
            target_chain,
            donor_chain,
            missing_atoms,
            superposition,
        )
        log.append(f"Added {atom_result.get('added_atom_count', 0)} atoms")

    if not copy_residues and not copy_atoms:
        parser = PDBParser(QUIET=True)
        struct = parser.get_structure("target", target_pdb)
        io = PDBIO()
        io.set_structure(struct)
        io.save(output_pdb)

    return {
        "output_file": output_pdb,
        "residue_copy": residue_result,
        "atom_copy": atom_result,
        "log": log,
    }


def donor_resids_from_range(
    donor_pdb: str,
    donor_chain: str,
    range_str: str,
) -> List[int]:
    """Validate and return donor residue numbers from a range string."""
    requested = parse_residue_range(range_str)
    parser = PDBParser(QUIET=True)
    struct = parser.get_structure("donor", donor_pdb)
    chain = _find_chain(struct, donor_chain)
    available = {r.id[1] for r in chain if r.id[0] == " "}
    missing = sorted(set(requested) - available)
    if missing:
        raise ValueError(
            f"Donor residues not found on chain {donor_chain}: {missing}"
        )
    return requested


def anchor_pairs_excluding_donor_resids(
    aligned_pairs: List[ResiduePair],
    exclude_resids: Set[int],
) -> List[ResiduePair]:
    return [p for p in aligned_pairs if p.donor_resid not in exclude_resids]
