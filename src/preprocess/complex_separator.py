"""
Complex Separator Tool
Automatically detects and separates protein, ligand, and ion components from PDB files
"""
from pathlib import Path
from typing import Dict, Any, Optional, List
from langchain.tools import tool


# Common ion residue names
COMMON_IONS = {
    'MG', 'CA', 'ZN', 'FE', 'NA', 'K', 'CL', 'MN', 'CU', 'NI', 'CO', 
    'MG2', 'CA2', 'ZN2', 'FE2', 'FE3', 'NA1', 'K1', 'CL1'
}

# Common water residue names
WATER_NAMES = {'HOH', 'TIP3', 'WAT', 'SOL', 'H2O', 'TIP', 'SPC'}


@tool
def separate_complex_components(
    pdb_file: str,
    output_dir: Optional[str] = None,
    protein_output: Optional[str] = None,
    ligand_output: Optional[str] = None,
    ion_output: Optional[str] = None
) -> Dict[str, Any]:
    """
    Automatically detect and separate all components (protein, ligands, ions) from a complex PDB file.
    Water molecules are automatically removed.
    
    Args:
        pdb_file: Input PDB file path containing protein complex
        output_dir: Output directory for separated files (optional)
        protein_output: Specific output path for protein (optional)
        ligand_output: Specific output path for ligand (optional)
        ion_output: Specific output path for ions (optional)
        
    Returns:
        Dict with success status, output file paths, and component statistics
    """
    try:
        import MDAnalysis as mda
    except ImportError:
        return {
            "success": False,
            "error": "MDAnalysis not installed. Install with: pip install MDAnalysis"
        }
    
    # Determine output directory
    base = Path(pdb_file).stem
    if output_dir:
        working_dir = Path(output_dir)
        working_dir.mkdir(parents=True, exist_ok=True)
    else:
        working_dir = Path(pdb_file).parent
    
    try:
        # Load the complex structure
        u = mda.Universe(pdb_file)
        
        # Select different components
        protein = u.select_atoms("protein")
        
        # Get all non-protein, non-water atoms
        non_protein_non_water = u.select_atoms("not protein and not (resname " + " ".join(WATER_NAMES) + ")")
        
        # Separate ions from ligands by checking residue names
        ions = None
        ligands = None
        
        if len(non_protein_non_water) > 0:
            # Identify ion residues
            ion_resnames = []
            ligand_resnames = []
            
            for residue in non_protein_non_water.residues:
                if residue.resname in COMMON_IONS:
                    ion_resnames.append(residue.resname)
                else:
                    ligand_resnames.append(residue.resname)
            
            # Select ions and ligands separately
            if ion_resnames:
                ion_selection = "resname " + " ".join(set(ion_resnames))
                ions = u.select_atoms(ion_selection)
            
            if ligand_resnames:
                ligand_selection = "resname " + " ".join(set(ligand_resnames))
                ligands = u.select_atoms(ligand_selection)
        
        # Prepare result dictionary
        result = {
            "success": True,
            "files_created": [],
            "statistics": {}
        }
        
        # Write protein if found
        if len(protein) > 0:
            if not protein_output:
                protein_output = str(working_dir / f"{base}_protein.pdb")
            protein.write(protein_output)
            result["protein_file"] = protein_output
            result["files_created"].append(protein_output)
            result["statistics"]["protein"] = {
                "atoms": len(protein),
                "residues": len(protein.residues),
                "chains": list(set(protein.chainIDs)),
                "resnames": list(set(protein.residues.resnames))[:10]
            }
        else:
            result["warnings"] = result.get("warnings", [])
            result["warnings"].append("No protein atoms found")
        
        # Write ligands if found
        if ligands is not None and len(ligands) > 0:
            if not ligand_output:
                ligand_output = str(working_dir / f"{base}_ligand.pdb")
            ligands.write(ligand_output)
            result["ligand_file"] = ligand_output
            result["files_created"].append(ligand_output)
            result["statistics"]["ligand"] = {
                "atoms": len(ligands),
                "residues": len(ligands.residues),
                "resnames": list(set(ligands.residues.resnames))
            }
        else:
            result["warnings"] = result.get("warnings", [])
            result["warnings"].append("No ligand molecules found")
        
        # Write ions if found
        if ions is not None and len(ions) > 0:
            if not ion_output:
                ion_output = str(working_dir / f"{base}_ions.pdb")
            ions.write(ion_output)
            result["ion_file"] = ion_output
            result["files_created"].append(ion_output)
            result["statistics"]["ions"] = {
                "atoms": len(ions),
                "residues": len(ions.residues),
                "resnames": list(set(ions.residues.resnames))
            }
        else:
            result["warnings"] = result.get("warnings", [])
            result["warnings"].append("No ion molecules found")
        
        # Add summary message
        components_found = []
        if "protein_file" in result:
            components_found.append(f"protein ({result['statistics']['protein']['atoms']} atoms)")
        if "ligand_file" in result:
            components_found.append(f"ligand ({result['statistics']['ligand']['atoms']} atoms)")
        if "ion_file" in result:
            components_found.append(f"ions ({result['statistics']['ions']['atoms']} atoms)")
        
        result["message"] = f"Successfully separated: {', '.join(components_found)}"
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to separate complex components: {str(e)}"
        }


def separate_protein_ligand(
    pdb_file: str,
    output_dir: Optional[str] = None,
    protein_output: Optional[str] = None,
    ligand_output: Optional[str] = None
) -> Dict[str, Any]:
    """
    Legacy function: Automatically detect and separate protein and ligand from a complex PDB file.
    This function now calls separate_complex_components for backward compatibility.
    
    NOTE: This function is NOT exposed as an LLM tool. Use separate_complex_components instead.
    Kept for backward compatibility in non-LLM contexts.
    
    Args:
        pdb_file: Input PDB file path containing protein-ligand complex
        output_dir: Output directory for separated files (optional)
        protein_output: Output PDB file path for protein (optional)
        ligand_output: Output PDB file path for ligand (optional)
        
    Returns:
        Dict with success status, protein_file, ligand_file paths, and component statistics
    """
    result = separate_complex_components(
        pdb_file=pdb_file,
        output_dir=output_dir,
        protein_output=protein_output,
        ligand_output=ligand_output
    )
    
    return result
