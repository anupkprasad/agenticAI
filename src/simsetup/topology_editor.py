"""
Topology Editor
Edits GROMACS topology files to include ligands, position restraints, and ions
Prevents duplicate entries and maintains proper formatting
"""
from pathlib import Path
from typing import Dict, Any, List, Optional
from langchain.tools import tool


class TopologyEditor:
    """Edit GROMACS topology files to include ligands and ions."""
    
    def edit_topology(
        self,
        topology_file: str,
        ligand_itp: Optional[str] = None,
        ligand_resname: Optional[str] = None,
        ligand_count: int = 1,
        ion_resname: Optional[str] = None,
        ion_count: Optional[int] = None,
        force_field_include: str = '#include "./amber99sb-ildn.ff/forcefield.itp"'
    ) -> Dict[str, Any]:
        """
        Edit topology file to include ligand and ion parameters.
        Prevents duplicate entries and maintains proper formatting.
        
        Args:
            topology_file: Path to topol.top file
            ligand_itp: Ligand topology file (e.g., "ATP.itp")
            ligand_resname: Ligand residue name (e.g., "ATP")
            ligand_count: Number of ligand molecules (default: 1)
            ion_resname: Ion residue name (e.g., "MG")
            ion_count: Number of ion molecules
            force_field_include: Force field include line to match
            
        Returns:
            Dict with success status and modifications made
        """
        try:
            topology_path = Path(topology_file)
            if not topology_path.exists():
                return {
                    "success": False,
                    "error": f"Topology file not found: {topology_file}"
                }
            
            # Read current topology
            with open(topology_path, "r") as f:
                lines = f.readlines()
            
            # Detect existing entries
            ligand_itp_included = False
            ligand_in_molecules = False
            ion_in_molecules = False
            
            if ligand_itp:
                ligand_itp_included = any(ligand_itp in line for line in lines)
            
            if ligand_resname:
                ligand_in_molecules = any(
                    ligand_resname in line.split()[:1] 
                    for line in lines 
                    if line.strip() and not line.strip().startswith(";")
                )
            
            if ion_resname:
                ion_in_molecules = any(
                    ion_resname in line.split()[:1]
                    for line in lines
                    if line.strip() and not line.strip().startswith(";")
                )
            
            # Track modifications
            modifications = []
            new_lines = []
            
            # Add ligand ITP include after force field include
            for line in lines:
                new_lines.append(line)
                
                if ligand_itp and not ligand_itp_included:
                    if force_field_include in line.strip():
                        # Extract ligand name for position restraints
                        if ligand_resname:
                            lig_name = ligand_resname
                        else:
                            lig_name = ligand_itp.split(".")[0]
                        
                        new_lines.append(f'#include "{ligand_itp}"\n')
                        new_lines.append(f'#ifdef POSRES_LIG\n')
                        new_lines.append(f'#include "posre_{lig_name}.itp"\n')
                        new_lines.append(f'#endif\n')
                        modifications.append(f"Added ligand include: {ligand_itp}")
                        ligand_itp_included = True
            
            lines = new_lines
            new_lines = []
            
            # Add molecules to [ molecules ] section
            molecules_found = False
            insert_index = None
            
            for i, line in enumerate(lines):
                new_lines.append(line)
                
                if line.strip().lower().startswith("[ molecules ]"):
                    molecules_found = True
                    # Find insert position (after existing molecules)
                    insert_index = i + 1
                    while insert_index < len(lines):
                        next_line = lines[insert_index].strip()
                        if next_line == "" or next_line.startswith(";"):
                            break
                        insert_index += 1
            
            # Insert ligand and ion entries
            if molecules_found and insert_index is not None:
                entries_to_add = []
                
                if ligand_resname and not ligand_in_molecules:
                    entries_to_add.append(f"{ligand_resname:<12} {ligand_count}\n")
                    modifications.append(f"Added ligand to molecules: {ligand_resname} x{ligand_count}")
                
                if ion_resname and ion_count and not ion_in_molecules:
                    entries_to_add.append(f"{ion_resname:<12} {ion_count}\n")
                    modifications.append(f"Added ion to molecules: {ion_resname} x{ion_count}")
                
                # Insert entries at proper location
                if entries_to_add:
                    for entry in reversed(entries_to_add):
                        new_lines.insert(insert_index, entry)
            
            # Write modified topology
            with open(topology_path, "w") as f:
                f.writelines(new_lines)
            
            return {
                "success": True,
                "topology_file": str(topology_path),
                "modifications": modifications,
                "ligand_included": ligand_itp_included,
                "ligand_in_molecules": ligand_in_molecules or (ligand_resname and not ligand_in_molecules),
                "ion_in_molecules": ion_in_molecules or (ion_resname and ion_count and not ion_in_molecules),
                "message": f"Topology updated with {len(modifications)} modifications"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to edit topology: {str(e)}"
            }


@tool
def edit_topology_file(
    topology_file: str,
    ligand_itp: Optional[str] = None,
    ligand_resname: Optional[str] = None,
    ligand_count: int = 1,
    ion_resname: Optional[str] = None,
    ion_count: Optional[int] = None
) -> Dict[str, Any]:
    """
    Edit GROMACS topology file to include ligand and ion parameters.
    Safely adds includes and molecule entries without creating duplicates.
    
    Args:
        topology_file: Path to topol.top file (generated by gmx pdb2gmx)
        ligand_itp: Ligand topology filename (e.g., "ATP.itp")
        ligand_resname: Ligand residue name (e.g., "ATP", "GTP")
        ligand_count: Number of ligand molecules in system (default: 1)
        ion_resname: Ion residue name (e.g., "MG", "MN", "ZN")
        ion_count: Number of ion molecules in system
    
    Returns:
        Dict with success status and list of modifications made
        
    Example:
        >>> edit_topology_file(
        ...     "topol.top",
        ...     ligand_itp="ATP.itp",
        ...     ligand_resname="ATP",
        ...     ion_resname="MG",
        ...     ion_count=2
        ... )
        {"success": True, "modifications": ["Added ligand include: ATP.itp", ...]}
        
    Note:
        - Detects and prevents duplicate entries
        - Adds position restraint support (#ifdef POSRES_LIG)
        - Adds entries to [ molecules ] section in correct order
    """
    editor = TopologyEditor()
    return editor.edit_topology(
        topology_file=topology_file,
        ligand_itp=ligand_itp,
        ligand_resname=ligand_resname,
        ligand_count=ligand_count,
        ion_resname=ion_resname,
        ion_count=ion_count
    )
