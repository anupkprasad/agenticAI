"""
PDB to GRO Converter
Converts PDB files to GROMACS GRO format using MDAnalysis
Handles protein, ligand, and ion components separately
"""
import MDAnalysis as mda
from pathlib import Path
from typing import Dict, Any, List, Optional
from langchain.tools import tool


class PDBtoGROConverter:
    """Convert PDB files to GRO format for GROMACS simulations."""
    
    def __init__(self, working_dir: str = "working_dir/simsetup"):
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
    
    def convert_pdb_to_gro(
        self,
        pdb_file: str,
        output_gro: str,
        selection: str = "all"
    ) -> Dict[str, Any]:
        """
        Convert a PDB file (or selection) to GRO format.
        
        Args:
            pdb_file: Input PDB file path
            output_gro: Output GRO file path
            selection: MDAnalysis selection string (default: "all")
            
        Returns:
            Dict with success status and file info
        """
        try:
            u = mda.Universe(pdb_file)
            atoms = u.select_atoms(selection)
            
            if len(atoms) == 0:
                return {
                    "success": False,
                    "error": f"No atoms found with selection: {selection}"
                }
            
            atoms.write(output_gro)
            
            return {
                "success": True,
                "output_file": output_gro,
                "n_atoms": len(atoms),
                "n_residues": len(atoms.residues),
                "selection": selection
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to convert {pdb_file}: {str(e)}"
            }
    
    def split_complex_to_gro(
        self,
        pdb_file: str,
        output_dir: Optional[str] = None,
        protein_output: str = "protein.gro",
        ligand_resname: Optional[str] = None,
        ligand_output: Optional[str] = None,
        ion_resname: Optional[str] = None,
        ion_output: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Split a complex PDB into separate GRO files for protein, ligand, and ions.
        
        Args:
            pdb_file: Input PDB file containing all components
            output_dir: Output directory (default: same as pdb_file)
            protein_output: Output filename for protein
            ligand_resname: Ligand residue name (e.g., "ATP")
            ligand_output: Output filename for ligand
            ion_resname: Ion residue name (e.g., "MG")
            ion_output: Output filename for ion
            
        Returns:
            Dict with paths to generated GRO files
        """
        if output_dir is None:
            output_dir = Path(pdb_file).parent
        else:
            output_dir = Path(output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            u = mda.Universe(pdb_file)
            results = {"success": True, "files": {}}
            
            # Convert protein
            protein = u.select_atoms("protein")
            if len(protein) > 0:
                protein_path = output_dir / protein_output
                protein.write(str(protein_path))
                results["files"]["protein"] = str(protein_path)
                results["protein_atoms"] = len(protein)
            
            # Convert ligand
            if ligand_resname:
                ligand = u.select_atoms(f"resname {ligand_resname}")
                if len(ligand) > 0:
                    if ligand_output is None:
                        ligand_output = f"{ligand_resname}.gro"
                    ligand_path = output_dir / ligand_output
                    ligand.write(str(ligand_path))
                    results["files"]["ligand"] = str(ligand_path)
                    results["ligand_atoms"] = len(ligand)
            
            # Convert ions with residue numbering fix
            if ion_resname:
                ions = u.select_atoms(f"resname {ion_resname}")
                if len(ions) > 0:
                    # Fix residue numbering to avoid conflicts
                    for i, residue in enumerate(ions.residues, start=1):
                        residue.resid = i
                    
                    if ion_output is None:
                        ion_output = f"{ion_resname}.gro"
                    ion_path = output_dir / ion_output
                    ions.write(str(ion_path))
                    results["files"]["ion"] = str(ion_path)
                    results["ion_atoms"] = len(ions)
                    results["ion_count"] = len(ions.residues)
            
            return results
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to split {pdb_file}: {str(e)}"
            }


@tool
def convert_pdb_to_gro(
    pdb_file: str,
    output_gro: str,
    selection: str = "all"
) -> Dict[str, Any]:
    """
    Convert PDB file to GROMACS GRO format using MDAnalysis.
    
    Args:
        pdb_file: Input PDB file path (e.g., "protein_h.pdb")
        output_gro: Output GRO file path (e.g., "protein.gro")
        selection: MDAnalysis selection string (default: "all")
                  Examples: "protein", "resname ATP", "resname MG"
    
    Returns:
        Dict with success status, output file path, and atom count
        
    Example:
        >>> convert_pdb_to_gro("protein_h.pdb", "protein.gro", "protein")
        {"success": True, "output_file": "protein.gro", "n_atoms": 1234}
    """
    converter = PDBtoGROConverter()
    return converter.convert_pdb_to_gro(pdb_file, output_gro, selection)


@tool
def split_complex_pdb_to_gro(
    pdb_file: str,
    output_dir: str,
    ligand_resname: Optional[str] = None,
    ion_resname: Optional[str] = None
) -> Dict[str, Any]:
    """
    Split a complex PDB file into separate GRO files for protein, ligand, and ions.
    Useful when you have a single PDB with all components together.
    
    Args:
        pdb_file: Input PDB file with all components (protein+ligand+ion)
        output_dir: Directory for output GRO files
        ligand_resname: Ligand residue name (e.g., "ATP", "GTP", "ADP")
        ion_resname: Ion residue name (e.g., "MG", "MN", "ZN")
    
    Returns:
        Dict with paths to generated protein.gro, ligand.gro, ion.gro files
        
    Example:
        >>> split_complex_pdb_to_gro(
        ...     "complex.pdb", 
        ...     "output/", 
        ...     ligand_resname="ATP", 
        ...     ion_resname="MG"
        ... )
        {"success": True, "files": {"protein": "output/protein.gro", ...}}
    """
    converter = PDBtoGROConverter()
    return converter.split_complex_to_gro(
        pdb_file=pdb_file,
        output_dir=output_dir,
        ligand_resname=ligand_resname,
        ion_resname=ion_resname
    )
