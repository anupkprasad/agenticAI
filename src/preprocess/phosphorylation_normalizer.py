"""
Map phosphorylated residue names/atoms for GROMACS force fields.

CHARMM36 (default pH 7.4): SEP/TPO/PTR → SP2/THP2/TP2 (dianionic), O3P→OT, drop H3T.
AMBER phospho: SEP→SP2, TPO→THP1 (THP in PDB), PTR→TP2.
Monoanionic CHARMM: keep SEP/TPO/PTR when requested in goal text.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from langchain.tools import tool

from src.preprocess.pdb_utils import reorder_pdb_by_resid, set_pdb_atom_name

from .phospho_residues import (
    ALL_PHOSPHO_PROTEIN_RESNAMES,
    DIANIONIC_DROP_ATOMS,
    PHOSPHO_ATOM_MAP,
    PhosphoIonicState,
    apply_resname_to_pdb_line,
    is_charmm_force_field,
    normalize_phospho_base_resname,
    parse_phospho_ionic_state,
    phospho_mapping_for_force_field,
    resname_from_pdb_line,
    target_resname_for_pdb_base,
)


def has_phosphorylated_residues(pdb_file: str) -> bool:
    """Return True if PDB contains any phosphorylated protein residue."""
    if not os.path.isfile(pdb_file):
        return False
    with open(pdb_file) as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            if resname_from_pdb_line(line) in ALL_PHOSPHO_PROTEIN_RESNAMES:
                return True
    return False


def needs_gromacs_phospho_mapping(
    pdb_file: str,
    force_field: str = "amber99sb-ildn",
    ionic_state: Optional[PhosphoIonicState] = None,
    user_text: str = "",
) -> bool:
    """Return True when phospho residues must be remapped for the target force field."""
    from .phospho_residues import needs_phospho_resname_mapping
    if ionic_state is None:
        ionic_state = parse_phospho_ionic_state(user_text, force_field)
    return needs_phospho_resname_mapping(pdb_file, force_field, ionic_state)


def _count_phospho_residues(pdb_file: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    with open(pdb_file) as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            base = normalize_phospho_base_resname(resname_from_pdb_line(line))
            if base:
                counts[base] = counts.get(base, 0) + 1
    return counts


def normalize_phosphorylation_pdb(
    pdb_file: str,
    output_file: str,
    force_field: str = "amber99sb-ildn",
    ionic_state: Optional[PhosphoIonicState] = None,
    user_text: str = "",
) -> Tuple[bool, Dict[str, int], str]:
    """
    Rewrite PDB with GROMACS-compatible phospho residue and atom names.

    Returns (changed, change_counts, message).
    """
    if not os.path.isfile(pdb_file):
        raise FileNotFoundError(f"PDB not found: {pdb_file}")

    if ionic_state is None:
        ionic_state = parse_phospho_ionic_state(user_text, force_field)

    mapping = phospho_mapping_for_force_field(force_field, ionic_state)
    use_dianionic_atoms = ionic_state == "dianionic" or (
        is_charmm_force_field(force_field) and ionic_state != "monoanionic"
    ) or ionic_state == "amber"

    resname_changes = 0
    atom_changes = 0
    atoms_dropped = 0
    output_lines: List[str] = []

    with open(pdb_file) as handle:
        for line in handle:
            if line.startswith(("ATOM", "HETATM")) and len(line) >= 20:
                base = resname_from_pdb_line(line)
                atom_name = line[12:16].strip()

                if use_dianionic_atoms and atom_name in DIANIONIC_DROP_ATOMS:
                    if normalize_phospho_base_resname(base):
                        atoms_dropped += 1
                        continue

                target = target_resname_for_pdb_base(base, force_field, ionic_state)
                current_field = line[17:21].strip().upper() if len(line) >= 21 else line[17:20].strip().upper()

                if base in mapping and target != base:
                    line = apply_resname_to_pdb_line(line, target)
                    resname_changes += 1
                elif target and current_field != target.upper() and base in mapping.values():
                    # Already mapped name but wrong field width (e.g. THP vs THP2)
                    if target != current_field[:len(target)]:
                        line = apply_resname_to_pdb_line(line, target)
                        resname_changes += 1

                phospho_base = normalize_phospho_base_resname(base) or normalize_phospho_base_resname(target)
                if phospho_base and use_dianionic_atoms:
                    new_atom = PHOSPHO_ATOM_MAP.get(atom_name)
                    if new_atom:
                        line = set_pdb_atom_name(line, new_atom)
                        atom_changes += 1

            output_lines.append(line)

    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as out:
        out.writelines(output_lines)

    changed = resname_changes > 0 or atom_changes > 0 or atoms_dropped > 0
    if changed:
        reorder_pdb_by_resid(output_file)
    counts = {
        "resname_changes": resname_changes,
        "atom_changes": atom_changes,
        "atoms_dropped": atoms_dropped,
    }
    if not changed:
        msg = f"No phosphorylation mapping required ({ionic_state}, {force_field})"
    else:
        targets = "/".join(sorted(set(mapping.values())))
        msg = (
            f"Mapped phosphorylation ({ionic_state}) → {targets}: "
            f"{resname_changes} residue records, {atom_changes} atom names, "
            f"{atoms_dropped} H3T atoms removed"
        )
    return changed, counts, msg


@tool
def normalize_phosphorylation_for_gromacs(
    pdb_file: str,
    output_file: Optional[str] = None,
    copy_to_protein: bool = True,
    force_field: str = "amber99sb-ildn",
    phospho_ionic_state: Optional[str] = None,
    user_text: str = "",
) -> Dict[str, object]:
    """
    Map phosphorylated residues for GROMACS pdb2gmx.

    CHARMM36 default (pH 7.4): dianionic SP2/THP2/TP2.
    Set phospho_ionic_state='monoanionic' or say "keep SEP/TPO" in user_text to keep native names.

    Args:
        pdb_file: Input PDB (typically protein.pdb after separation)
        output_file: Output path (default: protein_phospho_mapped.pdb)
        copy_to_protein: When True, also copy result to protein.pdb
        force_field: Target GROMACS force field
        phospho_ionic_state: 'dianionic', 'monoanionic', or 'amber'
        user_text: Goal text for parsing protonation preference

    Returns:
        Dict with success, change counts, and output paths
    """
    if not os.path.isfile(pdb_file):
        return {"success": False, "error": f"PDB file not found: {pdb_file}"}

    ionic_state: PhosphoIonicState = (
        phospho_ionic_state
        if phospho_ionic_state in ("dianionic", "monoanionic", "amber")
        else parse_phospho_ionic_state(user_text, force_field)
    )

    in_path = Path(pdb_file)
    out_path = Path(output_file) if output_file else in_path.parent / "protein_phospho_mapped.pdb"

    try:
        before = _count_phospho_residues(pdb_file)
        changed, counts, message = normalize_phosphorylation_pdb(
            pdb_file,
            str(out_path),
            force_field=force_field,
            ionic_state=ionic_state,
            user_text=user_text,
        )
        protein_path = in_path.parent / "protein.pdb"
        final_protein = str(protein_path)

        if changed and copy_to_protein:
            import shutil
            shutil.copy2(out_path, protein_path)
            final_protein = str(protein_path)

        return {
            "success": True,
            "changed": changed,
            "ionic_state": ionic_state,
            "output_file": str(out_path),
            "protein_file": final_protein if changed and copy_to_protein else pdb_file,
            "resnames_before": before,
            "resname_changes": counts["resname_changes"],
            "atom_changes": counts["atom_changes"],
            "atoms_dropped": counts.get("atoms_dropped", 0),
            "message": message,
        }
    except Exception as exc:
        return {"success": False, "error": str(exc)}
