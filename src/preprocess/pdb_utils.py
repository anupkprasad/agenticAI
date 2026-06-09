"""
PDB utilities for preprocessing workflows.
"""
from pathlib import Path
from typing import List, Tuple


def _parse_atom_line(line: str) -> Tuple[str, str, str, str]:
    """Return (record, chain_id, resname, resid) from an ATOM/HETATM line."""
    record = line[:6].strip()
    atom_name = line[12:16].strip()
    resname = line[17:20].strip()
    chain_id = line[21].strip() or " "
    resid = line[22:26].strip()
    return record, chain_id, resname, resid


def _format_ter(prev_line: str) -> str:
    """Build a TER record following the previous ATOM/HETATM line."""
    if len(prev_line) < 26:
        return "TER\n"
    serial = prev_line[6:11].strip()
    resname = prev_line[17:20]
    chain_id = prev_line[21]
    resid = prev_line[22:26]
    return f"TER   {serial:>5}      {resname:>3} {chain_id}{resid}\n"


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
