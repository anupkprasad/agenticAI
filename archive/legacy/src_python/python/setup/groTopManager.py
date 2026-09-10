#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on 2025-08-22 (Y/M/D) at 18:08
@author: Anup K. Prasad
email: anupkprasad121@gmail.com
"""
import MDAnalysis as mda
from MDAnalysis.coordinates.GRO import GROWriter
from MDAnalysis.core.universe import Merge
import sys
sys.path.append('/home/anup/myScripts/simulations/')
from createMappedPDB import apply_mapping_and_reorder
import pyrosetta

def edit_topology(top_path="topol.top", lig_itp="ATP.itp", metal_ion = "MG", metal_ion_count= None):
    """
    Safely edit a GROMACS topology file to include lig_itp and metal_ion parameters once.

    Args:
        top_path (str): Path to topology file (default: 'topol.top')
        lig_itp (str): ligand itp file name (default: 'ATP.itp')
        metal_ion_count (int): Number of Mg2+ ions to include (default: 2)
    """
    lig = lig_itp.split(".")[0]  # Extract ligand residue name from itp filename

    with open(top_path, "r") as f:
        lines = f.readlines()

    new_lines = []
    atp_included = any(lig_itp in line for line in lines)
    atp_in_molecules = any(lig in line.split()[:1] for line in lines if line.strip() and not line.strip().startswith(";"))
    mg_included = any(metal_ion in line.split()[:1] for line in lines if line.strip() and not line.strip().startswith(";"))

    # Copy lines and add includes only if not already present
    for line in lines:
        new_lines.append(line)
        if (
            line.strip().startswith('#include "./amber99sb-ildn.ff/forcefield.itp"')
            and not atp_included
        ):
            new_lines.append(f'#include "{lig_itp}"\n' + f'#ifdef POSRES_LIG\n#include "posre_{lig}.itp"\n#endif\n')

    # Insert ATP and MG entries under [ molecules ] section (only if not already there)
    molecules_section_found = False
    for i, line in enumerate(new_lines):
        if line.strip().lower().startswith("[ molecules ]"):
            molecules_section_found = True
            insert_index = i + 1
            # Find where molecule list ends
            while insert_index < len(new_lines) and new_lines[insert_index].strip() != "":
                insert_index += 1

            # Insert only if missing
            if not atp_in_molecules:
                new_lines.insert(insert_index, f"{lig}    1\n")
                insert_index += 1
            if metal_ion and metal_ion_count and not mg_included:
                new_lines.insert(insert_index, f"{metal_ion}     {metal_ion_count}\n")
            break

    with open(top_path, "w") as f:
        f.writelines(new_lines)

    print(f"Topology '{top_path}' safely updated (no duplicates added).")

    
def pdbToGr0(pdb_file, path = "./", ligand="ATP", metal_ion= None, pyro_init=True):
    if pyro_init:
        pyrosetta.init()
        pose = pyrosetta.pose_from_pdb(f"{path}/{pdb_file}")
        # Save structure with added hydrogens and coordinates
        pose.dump_pdb(f"{path}/{pdb_file.split('.')[0]}_h.pdb")
        ## mapping Ligand atom names
        apply_mapping_and_reorder(f"{path}/{pdb_file.split('.')[0]}_h.pdb", f"{path}/{pdb_file.split('.')[0]}_mapped.pdb", "/home/anup/myScripts/simulations/ATP_AF3_to_amber_mapping.txt", ligand_resname=ligand)
        #load structure with hydrogens and coordinates
        u = mda.Universe(f"{path}/{pdb_file.split('.')[0]}_mapped.pdb")
    else:
        u = mda.Universe(f"{path}/{pdb_file}")

    if metal_ion:
        # Optionally, reset residue numbers so they don’t conflict and delete duplicates MG
        for i, atom in enumerate(u.select_atoms("resname " + metal_ion).residues):
            print( atom.resid, i + 1 )
            atom.resid = i + 1

    protein = u.select_atoms("protein")
    atp = u.select_atoms("resname " + ligand)
    protein.write(f"{path}/protein.gro")
    atp.write(f"{path}/{ligand}.gro")
    if metal_ion:
        MI = u.select_atoms("resname " + metal_ion)
        MI.write(f"{path}/{metal_ion}.gro")
        print(f"Converted {pdb_file} to GRO files: protein.gro, ATP.gro, {metal_ion}.gro")
    else:
        print(f"Converted {pdb_file} to GRO files: protein.gro, ATP.gro")



def mergeGroFiles(gro_files, output_file = "complex.gro"):
    """
    Merge multiple GRO files into a single GRO file.
    Parameters:
    gro_files (list of str): List of paths to GRO files to be merged.
    output_file (str): Path to the output merged GRO file.
    """
    universes = [mda.Universe(gro) for gro in gro_files]
    merged = Merge(*[u.atoms for u in universes])

    with GROWriter(output_file, n_atoms=merged.atoms.n_atoms) as w:
        w.write(merged.atoms)

    print(f"Merged {len(gro_files)} GRO files into {output_file} with {merged.atoms.n_atoms} atoms.")




if __name__ == "__main__":
    # Example usage
    gro_files = ["protein_processed.gro", "ATP.gro", "MG.gro"]
    path = "/mnt/mydrive/pseudokinase/pseudoNcontrol_AF3/0_MD_simulation/atp_o14936kd2_kd2__amsa_atemp"
    gro_files = [f"{path}/{file}" for file in gro_files]
    mergeGroFiles(gro_files, output_file=f"{path}/complex.gro")