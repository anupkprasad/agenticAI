"""
PDB Structure Validation Tool
Validates PDB file integrity and reports issues/warnings
"""
import os
from typing import Dict, Any
from langchain.tools import tool


@tool
def validate_structure(pdb_file: str) -> Dict[str, Any]:
    """
    Validate PDB file structure and integrity.
    
    Args:
        pdb_file: PDB file path to validate
        
    Returns:
        Dict with validation results, issues, warnings, and statistics
    """
    try:
        issues = []
        warnings = []
        
        if not os.path.exists(pdb_file):
            return {
                "success": False,
                "error": f"File not found: {pdb_file}"
            }
        
        line_count = 0
        atom_count = 0
        hetatm_count = 0
        
        with open(pdb_file, 'r') as f:
            for line in f:
                line_count += 1
                if line.startswith("ATOM"):
                    atom_count += 1
                elif line.startswith("HETATM"):
                    hetatm_count += 1
        
        if atom_count == 0:
            issues.append("No ATOM records found in PDB file")
        
        if hetatm_count > 100:
            warnings.append(f"Large number of heteroatoms ({hetatm_count}) detected")
        
        return {
            "success": len(issues) == 0,
            "total_lines": line_count,
            "atoms": atom_count,
            "heteroatoms": hetatm_count,
            "issues": issues,
            "warnings": warnings,
            "message": f"Validation complete: {atom_count} atoms, {hetatm_count} heteroatoms"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Validation failed: {e}"
        }
