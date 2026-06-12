"""
Stage residuetypes.dat so pdb2gmx classifies phosphorylated amino acids as Protein.

GROMACS reads residuetypes.dat from the working directory before the system
copy. Without SP2/THP/TP2 (and PDB names SEP/TPO/PTR), pdb2gmx fails with:
  "residue THP173 is of type 'Other' ... add to residuetypes.dat"
"""
import logging
import os
import shutil
from pathlib import Path
from typing import Dict, Optional

from src.preprocess.phospho_residues import (
    ALL_PHOSPHO_PROTEIN_RESNAMES,
    is_phospho_protein_resname,
)

logger = logging.getLogger(__name__)

# CHARMM36 phospho names + common PDB names (all treated as protein)
_PHOSPHO_RESIDUETYPE_ENTRIES: Dict[str, str] = {
    name: "Protein" for name in sorted(ALL_PHOSPHO_PROTEIN_RESNAMES)
}
# Additional CHARMM36 variants not always in ALL_PHOSPHO_PROTEIN_RESNAMES
for _name in ("SP1", "THP1", "THP2", "TP1", "TP1A", "TP2A"):
    _PHOSPHO_RESIDUETYPE_ENTRIES[_name] = "Protein"


def _find_system_residuetypes_dat() -> Optional[Path]:
    """Locate the installed GROMACS residuetypes.dat."""
    gmxdata = os.environ.get("GMXDATA")
    if gmxdata:
        candidate = Path(gmxdata) / "top" / "residuetypes.dat"
        if candidate.is_file():
            return candidate

    gmx_bin = shutil.which("gmx")
    if gmx_bin:
        prefix = Path(gmx_bin).resolve().parent.parent
        candidate = prefix / "share" / "gromacs" / "top" / "residuetypes.dat"
        if candidate.is_file():
            return candidate

    return None


def _parse_residuetypes(path: Path) -> Dict[str, str]:
    entries: Dict[str, str] = {}
    with path.open() as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) >= 2:
                entries[parts[0].upper()] = parts[1]
    return entries


def _write_residuetypes(path: Path, entries: Dict[str, str]) -> None:
    lines = [f"{name}\t{entries[name]}\n" for name in sorted(entries)]
    path.write_text("".join(lines))


def _phospho_resnames_in_pdb(pdb_file: str) -> set:
    found: set = set()
    with open(pdb_file) as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")) or len(line) < 20:
                continue
            from src.preprocess.phospho_residues import resname_from_pdb_line
            resname = resname_from_pdb_line(line)
            if is_phospho_protein_resname(resname):
                found.add(resname)
    return found


def ensure_phospho_residuetypes_dat(
    working_dir: Path,
    pdb_file: Optional[str] = None,
) -> Optional[Path]:
    """
    Ensure ``working_dir/residuetypes.dat`` lists phospho residues as Protein.

    Copies the system residuetypes.dat if needed, then adds/updates phospho
    entries so pdb2gmx keeps them in the protein chain.
    """
    working_dir = Path(working_dir)
    working_dir.mkdir(parents=True, exist_ok=True)
    dest = working_dir / "residuetypes.dat"

    entries: Dict[str, str] = {}
    if dest.is_file():
        entries = _parse_residuetypes(dest)
    else:
        system_file = _find_system_residuetypes_dat()
        if system_file:
            entries = _parse_residuetypes(system_file)
        else:
            logger.warning("System residuetypes.dat not found; writing phospho-only overlay")

    # Always register known phospho names
    for name, rtype in _PHOSPHO_RESIDUETYPE_ENTRIES.items():
        entries[name.upper()] = rtype

    if pdb_file and os.path.isfile(pdb_file):
        for name in _phospho_resnames_in_pdb(pdb_file):
            entries[name.upper()] = "Protein"

    _write_residuetypes(dest, entries)
    logger.info("Staged residuetypes.dat for phospho protein residues: %s", dest)
    return dest


def pdb_has_phospho_residues(pdb_file: str) -> bool:
    """Return True if PDB contains any phosphorylated protein residue name."""
    if not os.path.isfile(pdb_file):
        return False
    return bool(_phospho_resnames_in_pdb(pdb_file))
