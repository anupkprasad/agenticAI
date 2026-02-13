"""
Atom Name Mapper
Maps ligand atom names from AlphaFold3/PDB format to AMBER force field format
Handles reordering atoms according to topology requirements
"""
import MDAnalysis as mda
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
from langchain.tools import tool


class AtomNameMapper:
    """Map and reorder ligand atom names for force field compatibility."""
    
    def read_mapping_file(
        self,
        mapping_file: str,
        ligand_resname: str
    ) -> Tuple[Dict[str, str], List[str]]:
        """
        Read atom name mapping file.
        
        Args:
            mapping_file: Path to mapping file
            ligand_resname: Ligand residue name to filter for
            
        Returns:
            Tuple of (mapping_dict, atom_order_list)
            
        Format:
            # Comment lines start with #
            RESNAME OLD_NAME NEW_NAME
            ATP PG P1G
            ATP O1G O1G
        """
        mapping = {}
        order = []
        
        with open(mapping_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                parts = line.split()
                if len(parts) < 3:
                    continue
                
                resname, old_name, new_name = parts[:3]
                if resname.strip() == ligand_resname:
                    mapping[old_name.strip()] = new_name.strip()
                    order.append(old_name.strip())
        
        if not mapping:
            raise ValueError(
                f"No mapping found for {ligand_resname} in {mapping_file}"
            )
        
        return mapping, order
    
    def apply_mapping_and_reorder(
        self,
        input_pdb: str,
        output_pdb: str,
        mapping_file: str,
        ligand_resname: str = "ATP"
    ) -> Dict[str, Any]:
        """
        Apply atom name mapping and reorder atoms for a ligand.
        Keeps other residues (protein, ions, waters) unchanged.
        
        Args:
            input_pdb: Input PDB file path
            output_pdb: Output PDB file path
            mapping_file: Atom name mapping file path
            ligand_resname: Ligand residue name (default: "ATP")
            
        Returns:
            Dict with success status and mapping statistics
        """
        try:
            # Read mapping
            mapping, order = self.read_mapping_file(mapping_file, ligand_resname)
            
            # Load structure
            u = mda.Universe(input_pdb)
            ligand = u.select_atoms(f"resname {ligand_resname}")
            
            if len(ligand) == 0:
                return {
                    "success": False,
                    "error": f"No atoms found with resname {ligand_resname}"
                }
            
            # Rename ligand atoms
            renamed_count = 0
            for atom in ligand.atoms:
                oldname = atom.name.strip()
                if oldname in mapping:
                    atom.name = mapping[oldname]
                    renamed_count += 1
            
            # Reorder ligand atoms
            reordered_atoms = []
            for oldname in order:
                newname = mapping[oldname]
                sel = ligand.select_atoms(f"name {newname}")
                reordered_atoms.extend(sel.atoms)
            
            # Add any unmapped atoms
            mapped_names = set(mapping.values())
            for atom in ligand.atoms:
                if atom.name not in mapped_names:
                    reordered_atoms.append(atom)
            
            # Reconstruct all atoms in correct order
            all_atoms = []
            ligand_added = False
            for res in u.residues:
                if res.resname == ligand_resname:
                    if not ligand_added:
                        all_atoms.extend(reordered_atoms)
                        ligand_added = True
                else:
                    all_atoms.extend(res.atoms)
            
            # Renumber atoms
            for i, atom in enumerate(all_atoms, start=1):
                atom.id = i
            
            # Write properly formatted PDB
            with open(output_pdb, "w") as fout:
                for atom in all_atoms:
                    segid = atom.segid if atom.segid else ""
                    element = atom.element if hasattr(atom, 'element') else atom.name[:2].strip()
                    
                    fout.write(
                        f"ATOM  {atom.id:5d} {atom.name:>4s} {atom.resname:>3s} "
                        f"{segid:>1s}{atom.resid:4d}    "
                        f"{atom.position[0]:8.3f}{atom.position[1]:8.3f}{atom.position[2]:8.3f}"
                        f"  1.00  0.00           {element:>2s}\n"
                    )
            
            return {
                "success": True,
                "input_file": input_pdb,
                "output_file": output_pdb,
                "ligand_resname": ligand_resname,
                "atoms_renamed": renamed_count,
                "atoms_reordered": len(reordered_atoms),
                "mapping_file": mapping_file,
                "message": f"Mapped and reordered {renamed_count} atoms for {ligand_resname}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to apply mapping: {str(e)}"
            }


@tool
def map_ligand_atom_names(
    input_pdb: str,
    output_pdb: str,
    mapping_file: str,
    ligand_resname: str = "ATP"
) -> Dict[str, Any]:
    """
    Map ligand atom names from AlphaFold3/PDB format to AMBER force field format.
    Also reorders atoms to match topology file requirements.
    
    Args:
        input_pdb: Input PDB file with original atom names
        output_pdb: Output PDB file with mapped atom names
        mapping_file: Atom name mapping file path
                     Format: RESNAME OLD_NAME NEW_NAME (one per line)
        ligand_resname: Ligand residue name (e.g., "ATP", "GTP", "ADP")
    
    Returns:
        Dict with success status, number of atoms renamed/reordered
        
    Example:
        >>> map_ligand_atom_names(
        ...     "complex_h.pdb",
        ...     "complex_mapped.pdb",
        ...     "ATP_AF3_to_amber_mapping.txt",
        ...     ligand_resname="ATP"
        ... )
        {"success": True, "atoms_renamed": 31, "atoms_reordered": 31}
        
    Note:
        - Only ligand atoms are renamed/reordered
        - Protein, ions, and water remain unchanged
        - Mapping file should contain: RESNAME OLD_ATOM NEW_ATOM per line
        - Lines starting with # are treated as comments
    """
    mapper = AtomNameMapper()
    return mapper.apply_mapping_and_reorder(
        input_pdb=input_pdb,
        output_pdb=output_pdb,
        mapping_file=mapping_file,
        ligand_resname=ligand_resname
    )
