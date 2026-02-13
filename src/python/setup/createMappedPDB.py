#!/usr/bin/env python3
import sys
import MDAnalysis as mda
from MDAnalysis.coordinates.PDB import PDBWriter


def read_mapping(mapping_file):
    """Reads mapping file and returns dictionary {(resname, old_atom): new_atom}"""
    mapping = {}
    with open(mapping_file) as f:
        for line in f:
            if line.strip().startswith("#") or not line.strip():
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            resname, old_atom, new_atom = parts[:3]
            mapping[(resname, old_atom)] = new_atom
    return mapping


def apply_mapping(pdb_in, pdb_out, mapping_file):
    mapping = read_mapping(mapping_file)
    """Reads PDB, replaces atom names according to mapping, and writes output"""
    with open(pdb_in) as fin, open(pdb_out, "w") as fout:
        for line in fin:
            if line.startswith(("ATOM", "HETATM")):
                resname = line[17:20].strip()
                atom_name = line[12:16].strip()

                key = (resname, atom_name)
                if key in mapping:
                    new_name = mapping[key]
                    # Replace atom name while keeping column formatting (cols 13–16)
                    line = line[:12] + new_name.rjust(4) + line[16:]
            fout.write(line)


def apply_mapping_and_reorder(
    pdb_in: str,
    pdb_out: str,
    mapping_file: str,
    ligand_resname: str = "ATP"
):
    """
    Apply atom name mapping and reorder atoms for a ligand in a PDB file.
    Keeps other residues (protein, ions, waters) unchanged.
    """
    # --- Read mapping ---
    mapping = {}
    order = []
    with open(mapping_file) as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                res, old, new = parts[:3]
                if res.strip() == ligand_resname:
                    mapping[old.strip()] = new.strip()
                    order.append(old.strip())

    if not mapping:
        raise ValueError(f"No mapping found for {ligand_resname} in {mapping_file}")

    # --- Load structure ---
    u = mda.Universe(pdb_in)
    ligand = u.select_atoms(f"resname {ligand_resname}")
    if len(ligand) == 0:
        raise ValueError(f"No atoms found with resname {ligand_resname}")

    # --- Rename ligand atoms based on mapping ---
    for atom in ligand.atoms:
        oldname = atom.name.strip()
        if oldname in mapping:
            atom.name = mapping[oldname]

    # --- Reorder ligand atoms as per mapping order ---
    reordered_atoms = []
    for oldname in order:
        newname = mapping[oldname]
        sel = ligand.select_atoms(f"name {newname}")
        reordered_atoms.extend(sel.atoms)

    # Add unmapped atoms if any
    mapped_names = {mapping[o] for o in mapping}
    for atom in ligand.atoms:
        if atom.name not in mapped_names:
            reordered_atoms.append(atom)

    # --- Reconstruct all atoms in correct order ---
    all_atoms = []
    for res in u.residues:
        if res.resname == ligand_resname:
            all_atoms.extend(reordered_atoms)
        else:
            all_atoms.extend(res.atoms)

    # --- Renumber atoms ---
    for i, atom in enumerate(all_atoms, start=1):
        atom.id = i

    # --- Write properly formatted PDB ---
    with open(pdb_out, "w") as fout:
        for atom in all_atoms:
            fout.write(
                f"ATOM  {atom.id:5d} {atom.name:>4s} {atom.resname:>3s} {atom.segid:>1s}"
                f"{atom.resid:4d}    {atom.position[0]:8.3f}{atom.position[1]:8.3f}{atom.position[2]:8.3f}"
                f"  1.00  0.00           {atom.element:>2s}\n"
            )

    print(f"Corrected + reordered ligand ({ligand_resname}) written to {pdb_out}")



def main():
    if len(sys.argv) != 4:
        print("Usage: python apply_atomname_mapping.py input.pdb mapping.txt output.pdb")
        sys.exit(1)

    pdb_in, mapping_file, pdb_out = sys.argv[1:4]
    mapping = read_mapping(mapping_file)
    apply_mapping_and_reorder(pdb_in, pdb_out, mapping)
    print(f"Mapping applied successfully. Output written to: {pdb_out}")


if __name__ == "__main__":
    #main()
    pdb_in = "/mnt/mydrive/pseudokinase/pseudoNcontrol_AF3/0_MD_simulation/test/0.pdb"
    mapping= "/home/anup/myScripts/simulations/ATP_AF3_to_amber_mapping.txt"
    pdb_out = "/mnt/mydrive/pseudokinase/pseudoNcontrol_AF3/0_MD_simulation/test/output.pdb"
    apply_mapping_and_reorder(pdb_in, pdb_out, mapping)
