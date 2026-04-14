"""
Topology Editor
Edits GROMACS topology files to include ligands, position restraints, and ions
Prevents duplicate entries and maintains proper formatting
"""
import re as _re
from pathlib import Path
from typing import Dict, Any, List, Optional


def _get_moleculetype_from_itp(itp_file: str, topology_dir: Optional[Path] = None) -> Optional[str]:
    """
    Read the moleculetype name from the [ moleculetype ] section of an ITP file.
    Acpype names the moleculetype after the stem of the input PDB (e.g. ATP_h),
    which may differ from the residue name in the structure (e.g. ATP).
    Returns the name string, or None if not found.
    """
    itp_path = Path(itp_file)
    # If not an absolute/resolvable path, look next to the topology file
    if not itp_path.exists() and topology_dir:
        itp_path = topology_dir / itp_path.name
    if not itp_path.exists():
        return None
    try:
        in_section = False
        with open(itp_path) as f:
            for line in f:
                stripped = line.strip()
                if _re.match(r'\[\s*moleculetype\s*\]', stripped, _re.I):
                    in_section = True
                    continue
                if in_section:
                    if stripped.startswith('['):
                        break  # entered next section
                    if stripped and not stripped.startswith(';'):
                        parts = stripped.split()
                        if parts:
                            return parts[0]
        return None
    except Exception:
        return None


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
        force_field_include: str = '#include "amber99sb-ildn.ff/forcefield.itp"'
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
            force_field_include: Force field include line to match (substring)
            
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

            # Determine the actual moleculetype name from the ITP file.
            # Acpype stores the moleculetype as the stem of the input PDB
            # (e.g. ATP_h from ATP_h.pdb → ATP_h_GMX.itp), which may differ
            # from the residue name in the structure (e.g. ATP).
            mol_entry_name = ligand_resname  # default fallback
            if ligand_itp:
                itp_moltype = _get_moleculetype_from_itp(ligand_itp, topology_path.parent)
                if itp_moltype:
                    mol_entry_name = itp_moltype
                else:
                    # Fallback: strip _GMX suffix from ITP basename stem
                    itp_stem = Path(ligand_itp).stem  # e.g. ATP_h_GMX
                    if itp_stem.upper().endswith('_GMX'):
                        mol_entry_name = itp_stem[:-4]  # e.g. ATP_h
                    else:
                        mol_entry_name = itp_stem

            # Read current topology
            with open(topology_path, "r") as f:
                lines = f.readlines()

            # Detect existing entries
            ligand_itp_included = False
            ligand_in_molecules = False
            ion_in_molecules = False

            if ligand_itp:
                # Match by basename so both absolute and relative paths are detected
                ligand_itp_basename = Path(ligand_itp).name
                ligand_itp_included = any(
                    ligand_itp_basename in line or ligand_itp in line
                    for line in lines
                )

            if mol_entry_name:
                # Check for either mol_entry_name OR ligand_resname already present
                check_names = {mol_entry_name}
                if ligand_resname:
                    check_names.add(ligand_resname)
                ligand_in_molecules = any(
                    line.split()[:1] and line.split()[0] in check_names
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
            # Use flexible matching: strip "./" prefix, match substring
            ff_match_key = force_field_include.replace('./', '')
            for line in lines:
                new_lines.append(line)
                
                if ligand_itp and not ligand_itp_included:
                    stripped = line.strip().replace('./', '')
                    if ff_match_key in stripped:
                        # Always use basename in #include so grompp finds it
                        # relative to the topology file directory
                        itp_include_name = Path(ligand_itp).name
                        new_lines.append(f'#include "{itp_include_name}"\n')
                        new_lines.append(f'#ifdef POSRES_LIG\n')
                        # posre file is posre_{moltype}.itp (acpype convention)
                        new_lines.append(f'#include "posre_{mol_entry_name}.itp"\n')
                        new_lines.append(f'#endif\n')
                        modifications.append(f"Added ligand include: {itp_include_name}")
                        ligand_itp_included = True
            
            lines = new_lines
            new_lines = []
            
            # Add molecules to [ molecules ] section
            # We need to insert ligand/ion entries AFTER existing molecule lines
            # (e.g. after "Protein  1") to match the order in complex.gro:
            # protein first, then ligand, then ions.
            molecules_found = False
            insert_index = None
            
            for i, line in enumerate(lines):
                new_lines.append(line)
                
                if line.strip().lower().startswith("[ molecules ]"):
                    molecules_found = True
                    # Scan forward past comments, blanks, and existing molecule entries
                    # to find the insertion point AFTER the last molecule line.
                    insert_index = i + 1
                    while insert_index < len(lines):
                        next_line = lines[insert_index].strip()
                        if next_line == "" or next_line.startswith(";"):
                            # Skip empty lines and comments
                            insert_index += 1
                            continue
                        # This is a molecule entry — keep scanning past it
                        if next_line and not next_line.startswith("["):
                            insert_index += 1
                            continue
                        break  # Hit next section header or EOF
            
            # Insert ligand and ion entries
            if molecules_found and insert_index is not None:
                entries_to_add = []

                if mol_entry_name and not ligand_in_molecules:
                    entries_to_add.append(f"{mol_entry_name:<12} {ligand_count}\n")
                    modifications.append(f"Added ligand to molecules: {mol_entry_name} x{ligand_count}")

                if ion_resname and ion_count and not ion_in_molecules:
                    entries_to_add.append(f"{ion_resname:<12} {ion_count}\n")
                    modifications.append(f"Added ion to molecules: {ion_resname} x{ion_count}")
                
                # Append entries AFTER existing molecules (Protein first,
                # then ligand, then ions) so the order matches complex.gro
                if entries_to_add:
                    for entry in entries_to_add:
                        new_lines.insert(insert_index, entry)
                        insert_index += 1
            
            # Write modified topology
            with open(topology_path, "w") as f:
                f.writelines(new_lines)
            
            return {
                "success": True,
                "topology_file": str(topology_path),
                "modifications": modifications,
                "ligand_included": ligand_itp_included,
                "ligand_in_molecules": ligand_in_molecules or (mol_entry_name and not ligand_in_molecules),
                "ion_in_molecules": ion_in_molecules or (ion_resname and ion_count and not ion_in_molecules),
                "message": f"Topology updated with {len(modifications)} modifications"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to edit topology: {str(e)}"
            }


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
