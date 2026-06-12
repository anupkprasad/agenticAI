"""
Phosphorylated amino acid residue names for preprocessing and GROMACS setup.

These are protein residues, not small-molecule ligands — they must stay in the
protein chain for pdb2gmx (with phospho-compatible force field parameters).
"""
import re
from typing import Dict, FrozenSet, Literal, Optional, Set

# Names in PDB / AlphaFold structures
PDB_PHOSPHO_RESNAMES: FrozenSet[str] = frozenset({"SEP", "TPO", "PTR"})

# GROMACS / CHARMM phospho names (after normalization)
GROMACS_PHOSPHO_RESNAMES: FrozenSet[str] = frozenset({
    "SP1", "SP2", "THP1", "THP", "THP2", "TP1", "TP2",
})

# AMBER phospho mapping (amber99sb-ildn + phospho parameters)
PDB_TO_AMBER_GROMACS_RESNAME_MAP: Dict[str, str] = {
    "SEP": "SP2",
    "TPO": "THP1",
    "PTR": "TP2",
}

# CHARMM36 dianionic (default at pH 7.4): SP2 / THP2 / TP2 rtp entries
PDB_TO_CHARMM_DIANIONIC_MAP: Dict[str, str] = {
    "SEP": "SP2",
    "TPO": "THP2",
    "PTR": "TP2",
}

# CHARMM36 monoanionic: keep PDB names that match monoanionic rtp (O3P + H3T)
PDB_TO_CHARMM_MONOANIONIC_MAP: Dict[str, str] = {
    "SEP": "SEP",
    "TPO": "TPO",
    "PTR": "PTR",
}

ALL_PHOSPHO_PROTEIN_RESNAMES: FrozenSet[str] = (
    PDB_PHOSPHO_RESNAMES | GROMACS_PHOSPHO_RESNAMES
)

# AMBER: THP1 is written as THP in the 3-character PDB column
GROMACS_TO_PDB_RESNAME_FIELD: Dict[str, str] = {
    "SP2": "SP2",
    "THP1": "THP",
    "TP2": "TP2",
}

# Phosphate oxygen: O3P → OT on dianionic CHARMM / AMBER phospho residues
PHOSPHO_ATOM_MAP: Dict[str, str] = {"O3P": "OT"}

# Atoms removed when converting monoanionic → dianionic (proton on phosphate)
DIANIONIC_DROP_ATOMS: FrozenSet[str] = frozenset({"H3T"})

PhosphoIonicState = Literal["dianionic", "monoanionic", "amber"]

_DIGIT_PREFIX_RE = re.compile(r"^\d+")


def normalize_phospho_base_resname(resname: str) -> Optional[str]:
    """
    Return canonical phospho base name (SEP/TPO/PTR/SP2/THP1/TP2) if phosphorylated.
    """
    r = resname.strip().upper()
    if r in ALL_PHOSPHO_PROTEIN_RESNAMES:
        return r
    stripped = _DIGIT_PREFIX_RE.sub("", r)
    if stripped in ALL_PHOSPHO_PROTEIN_RESNAMES:
        return stripped
    if r == "THP":
        return "THP1"
    return None


def resname_from_pdb_line(line: str) -> str:
    """Extract phosphorylated (or any) residue name from an ATOM/HETATM line."""
    if len(line) < 20:
        return ""
    r3 = line[17:20].strip().upper()
    if len(line) >= 21:
        r4 = line[17:21].strip().upper()
        base4 = normalize_phospho_base_resname(r4)
        if base4:
            return base4
    base3 = normalize_phospho_base_resname(r3)
    if base3:
        return base3
    # CHARMM-style: column 17 digit + 3-letter name in 18-20 (e.g. "1" + "TPO")
    if len(line) >= 21 and line[17].isdigit():
        suffix = line[18:21].strip().upper()
        if suffix in PDB_PHOSPHO_RESNAMES:
            return suffix
    return r3


def is_phospho_protein_resname(resname: str) -> bool:
    return normalize_phospho_base_resname(resname) is not None


def is_charmm_force_field(force_field: str) -> bool:
    return "charmm" in (force_field or "").lower()


def parse_phospho_ionic_state(
    text: str = "",
    force_field: str = "amber99sb-ildn",
) -> PhosphoIonicState:
    """
  Parse user text for phospho protonation preference.

  Default: CHARMM → dianionic (SP2/THP2/TP2 at pH 7.4); AMBER → amber mapping.
    """
    lower = (text or "").lower()
    mono_patterns = (
        "monoanionic", "mono-anionic", "mono anionic",
        "keep sep", "keep tpo", "keep ptr", "native sep", "native tpo", "native ptr",
        "native phospho", "sp1", "thp1", "tp1", "seph", "tpoh",
    )
    di_patterns = (
        "dianionic", "di-anionic", "di anionic", "fully deprotonated",
        "sp2", "thp2", "tp2",
    )
    if any(p in lower for p in mono_patterns):
        return "monoanionic"
    if any(p in lower for p in di_patterns):
        return "dianionic"
    if is_charmm_force_field(force_field):
        return "dianionic"
    return "amber"


def phospho_mapping_for_force_field(
    force_field: str,
    ionic_state: PhosphoIonicState,
) -> Dict[str, str]:
    """Return PDB base → target resname map for the chosen FF and ionic state."""
    if ionic_state == "monoanionic" or (
        is_charmm_force_field(force_field) and ionic_state != "dianionic"
    ):
        if is_charmm_force_field(force_field):
            return dict(PDB_TO_CHARMM_MONOANIONIC_MAP)
    if is_charmm_force_field(force_field):
        return dict(PDB_TO_CHARMM_DIANIONIC_MAP)
    return dict(PDB_TO_AMBER_GROMACS_RESNAME_MAP)


def target_resname_for_pdb_base(
    base_resname: str,
    force_field: str,
    ionic_state: PhosphoIonicState,
) -> str:
    """Map SEP/TPO/PTR base to target residue name for the force field."""
    base = normalize_phospho_base_resname(base_resname) or base_resname.upper()
    if base in PDB_PHOSPHO_RESNAMES:
        mapping = phospho_mapping_for_force_field(force_field, ionic_state)
        return mapping.get(base, base)
    return base_resname


def apply_resname_to_pdb_line(line: str, new_resname: str) -> str:
    """
    Write ``new_resname`` into a PDB ATOM line (handles 3- and 4-char CHARMM names).

    CHARMM structures use columns 17-20 as a 4-character residue field (e.g. ``1SEP``,
    ``1TPO``). Three-letter targets keep the leading digit (``1SP2``); four-letter
    targets (``THP2``) replace the whole field.
    """
    if len(line) < 22:
        return line
    new_resname = new_resname.upper()
    if line[17].isdigit():
        if len(new_resname) == 3:
            field = line[17] + new_resname
        elif len(new_resname) >= 4:
            field = new_resname[:4]
        else:
            field = f"{line[17]}{new_resname:>3}"[:4]
        return line[:17] + field + line[21:]
    if len(new_resname) <= 3:
        return line[:17] + f"{new_resname:>3}" + line[20:]
    return line[:17] + new_resname[:4] + line[21:]


def pdb_resname_field_for_gromacs(gromacs_resname: str, force_field: str = "") -> str:
    """Format residue name for PDB column(s); AMBER THP1 → THP."""
    if not is_charmm_force_field(force_field):
        key = gromacs_resname.upper()
        if key in GROMACS_TO_PDB_RESNAME_FIELD:
            return GROMACS_TO_PDB_RESNAME_FIELD[key]
    key = gromacs_resname.upper()
    if len(key) <= 3:
        return key
    return key  # THP2 written via apply_resname_to_pdb_line


def needs_phospho_resname_mapping(
    pdb_file: str,
    force_field: str = "amber99sb-ildn",
    ionic_state: Optional[PhosphoIonicState] = None,
) -> bool:
    """Return True when PDB phospho names must be rewritten for the target FF."""
    if ionic_state is None:
        ionic_state = parse_phospho_ionic_state("", force_field)
    if ionic_state == "monoanionic" and is_charmm_force_field(force_field):
        return False
    mapping = phospho_mapping_for_force_field(force_field, ionic_state)
    import os
    if not os.path.isfile(pdb_file):
        return False
    with open(pdb_file) as handle:
        for line in handle:
            if not line.startswith(("ATOM", "HETATM")):
                continue
            base = resname_from_pdb_line(line)
            if base in PDB_PHOSPHO_RESNAMES and mapping.get(base, base) != base:
                return True
            # Already SP2 but still has O3P/H3T (monoanionic atoms)
            if base in mapping.values():
                atom = line[12:16].strip()
                if atom in DIANIONIC_DROP_ATOMS or atom == "O3P":
                    if ionic_state == "dianionic":
                        return True
    return False


def gromacs_resname_for_pdb_resname(
    resname: str,
    force_field: str = "amber99sb-ildn",
    ionic_state: Optional[PhosphoIonicState] = None,
) -> str:
    """Map PDB phospho name to target GROMACS/CHARMM residue name."""
    if ionic_state is None:
        ionic_state = parse_phospho_ionic_state("", force_field)
    base = normalize_phospho_base_resname(resname)
    if base and base in PDB_PHOSPHO_RESNAMES:
        mapping = phospho_mapping_for_force_field(force_field, ionic_state)
        return mapping.get(base, base)
    return resname


def phospho_resname_mda_selection(extra_resnames: Optional[Set[str]] = None) -> str:
    """MDAnalysis selection fragment: ``resname SEP TPO PTR SP2 ...``."""
    names = set(ALL_PHOSPHO_PROTEIN_RESNAMES)
    if extra_resnames:
        names.update(extra_resnames)
    return "resname " + " ".join(sorted(names))


def phospho_resnames_in_universe(universe) -> Set[str]:
    """Actual resnames in a structure that qualify as phosphorylated protein."""
    found: Set[str] = set()
    for residue in universe.residues:
        if is_phospho_protein_resname(residue.resname):
            found.add(residue.resname)
    return found


def select_phospho_protein_atoms(universe):
    """Return AtomGroup of all phosphorylated protein residues in ``universe``."""
    indices = []
    for residue in universe.residues:
        if is_phospho_protein_resname(residue.resname):
            indices.extend(residue.atoms.indices.tolist())
    if not indices:
        return universe.atoms[[]]
    import numpy as np
    return universe.atoms[np.unique(indices)]
