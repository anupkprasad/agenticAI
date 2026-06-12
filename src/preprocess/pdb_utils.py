"""
PDB utilities for preprocessing workflows.
"""
from pathlib import Path
from typing import List, Tuple


def format_pdb_atom_name_field(atom_name: str) -> str:
    """Format an atom name for PDB columns 13-16 (CHARMM/GROMACS-safe)."""
    name = atom_name.strip()
    if len(name) >= 4:
        return name[:4]
    if len(name) == 3:
        return (" " + name) if name[0].isalpha() else name
    if len(name) == 2:
        if name[0].isdigit():
            return name + " "
        return " " + name + " "
    if len(name) == 1:
        return " " + name + "  "
    return f"{name:>4}"[:4]


def set_pdb_atom_name(line: str, atom_name: str) -> str:
    """Set PDB atom name (columns 13-16) on an ATOM/HETATM line."""
    if len(line) < 16:
        return line
    return line[:12] + format_pdb_atom_name_field(atom_name) + line[16:]


def _parse_atom_line(line: str) -> Tuple[str, str, str, str]:
    """Return (record, chain_id, resname, resid) from an ATOM/HETATM line."""
    from src.preprocess.phospho_residues import resname_from_pdb_line

    record = line[:6].strip()
    chain_id = line[21].strip() if len(line) > 21 else " "
    resid = line[22:26].strip() if len(line) > 26 else ""
    resname = resname_from_pdb_line(line) if len(line) >= 20 else line[17:20].strip()
    return record, chain_id, resname, resid


def _format_ter(prev_line: str) -> str:
    """Build a TER record following the previous ATOM/HETATM line."""
    if len(prev_line) < 26:
        return "TER\n"
    serial = prev_line[6:11].strip()
    _, chain_id, resname, resid = _parse_atom_line(prev_line)
    res_field = f"{resname:>3}"[:3]
    return f"TER   {serial:>5}      {res_field} {chain_id}{resid:>4}\n"


def reorder_pdb_by_resid(pdb_file: str, output_file: str | None = None) -> str:
    """
    Sort ATOM/HETATM records by chain ID and residue number, then re-insert TER.

    MDAnalysis may write phosphorylated residues at the end of the file when they
    are appended to the standard protein selection.
    """
    pdb_path = Path(pdb_file)
    out_path = Path(output_file) if output_file else pdb_path

    with pdb_path.open() as handle:
        lines = handle.readlines()

    header: List[str] = []
    atom_lines: List[str] = []
    footer: List[str] = []
    past_atoms = False

    for line in lines:
        record = line[:6].strip()
        if record in {"ATOM", "HETATM"}:
            atom_lines.append(line)
            past_atoms = True
        elif record == "TER":
            continue
        elif record == "END" or past_atoms:
            footer.append(line)
            past_atoms = True
        else:
            header.append(line)

    def _sort_key(line: str) -> tuple:
        chain = line[21] if len(line) > 21 else ""
        try:
            resid = int(line[22:26].strip())
        except ValueError:
            resid = 0
        try:
            serial = int(line[6:11].strip())
        except ValueError:
            serial = 0
        return (chain, resid, serial)

    atom_lines.sort(key=_sort_key)

    with out_path.open("w") as handle:
        handle.writelines(header)
        handle.writelines(atom_lines)
        handle.writelines(footer)

    insert_ter_records(str(out_path))
    return str(out_path)


def insert_ter_records(pdb_file: str, output_file: str | None = None) -> str:
    """
    Insert TER records at protein chain boundaries in a PDB file.

    MDAnalysis PDBWriter drops TER cards. GROMACS pdb2gmx uses TER (and chain
    IDs) to detect C-termini and handle OXT atoms correctly in multi-chain
    structures.

    Args:
        pdb_file: Input PDB path.
        output_file: Optional output path; overwrites input when omitted.

    Returns:
        Path to the PDB file with TER records inserted.
    """
    pdb_path = Path(pdb_file)
    out_path = Path(output_file) if output_file else pdb_path

    with pdb_path.open() as handle:
        lines = handle.readlines()

    output: List[str] = []
    prev_atom_line: str | None = None
    prev_chain: str | None = None

    for line in lines:
        record = line[:6].strip()
        if record in {"ATOM", "HETATM"}:
            _, chain_id, _, _ = _parse_atom_line(line)
            if (
                prev_atom_line is not None
                and prev_chain is not None
                and chain_id != prev_chain
                and (not output or output[-1][:3] != "TER")
            ):
                output.append(_format_ter(prev_atom_line))
            output.append(line)
            prev_atom_line = line
            prev_chain = chain_id
        elif record == "TER":
            if output and output[-1][:3] == "TER":
                continue
            output.append(line)
            prev_atom_line = None
            prev_chain = None
        else:
            output.append(line)

    if prev_atom_line is not None and (not output or output[-1][:3] != "TER"):
        output.append(_format_ter(prev_atom_line))

    with out_path.open("w") as handle:
        handle.writelines(output)

    return str(out_path)
