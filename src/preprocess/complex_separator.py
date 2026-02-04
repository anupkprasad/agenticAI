"""
Complex Separator Tool
Automatically detects and separates protein and ligand components from PDB files
"""
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool


@tool
def separate_protein_ligand(
    pdb_file: str,
    protein_output: Optional[str] = None,
    ligand_output: Optional[str] = None
) -> Dict[str, Any]:
    """
    Automatically detect and separate protein and ligand from a complex PDB file.
    
    Args:
        pdb_file: Input PDB file path containing protein-ligand complex
        protein_output: Output PDB file path for protein (optional)
        ligand_output: Output PDB file path for ligand (optional)
        
    Returns:
        Dict with success status, protein_file, ligand_file paths, and component statistics
    """
    try:
        import MDAnalysis as mda
    except ImportError:
        return {
            "success": False,
            "error": "MDAnalysis not installed. Install with: pip install MDAnalysis"
        }
    
    # Set default output paths if not provided
    if not protein_output:
        base = Path(pdb_file).stem
        working_dir = Path(pdb_file).parent
        protein_output = str(working_dir / f"{base}_protein.pdb")
    
    if not ligand_output:
        base = Path(pdb_file).stem
        working_dir = Path(pdb_file).parent
        ligand_output = str(working_dir / f"{base}_ligand.pdb")
    
    try:
        # Load the complex structure
        u = mda.Universe(pdb_file)
        
        # Select protein and ligand components
        protein = u.select_atoms("protein")
        ligand = u.select_atoms("not protein and not resname HOH and not ion")
        
        # Check if components were found
        if len(protein) == 0:
            return {
                "success": False,
                "error": "No protein atoms found in PDB file"
            }
        
        if len(ligand) == 0:
            return {
                "success": False,
                "error": "No ligand atoms found in PDB file (only protein, water, and ions detected)",
                "warning": "Consider using this tool only for protein-ligand complexes"
            }
        
        # Write separated components
        protein.write(protein_output)
        ligand.write(ligand_output)
        
        # Collect statistics
        protein_residues = list(set(protein.residues.resnames))
        ligand_residues = list(set(ligand.residues.resnames))
        
        return {
            "success": True,
            "protein_file": protein_output,
            "ligand_file": ligand_output,
            "message": f"Separated protein ({len(protein)} atoms) and ligand ({len(ligand)} atoms)",
            "statistics": {
                "protein_atoms": len(protein),
                "protein_residues": len(protein.residues),
                "protein_chains": list(set(protein.chainIDs)),
                "protein_resnames": protein_residues[:10],  # First 10 for brevity
                "ligand_atoms": len(ligand),
                "ligand_residues": len(ligand.residues),
                "ligand_resnames": ligand_residues
            }
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to separate protein and ligand: {str(e)}"
        }
