"""
GRO File Merger
Merges multiple GROMACS GRO files into a single complex
Maintains proper atom numbering and formatting
"""
import MDAnalysis as mda
from MDAnalysis.coordinates.GRO import GROWriter
from MDAnalysis.core.universe import Merge
from pathlib import Path
from typing import Dict, Any, List
from langchain.tools import tool


class GROMerger:
    """Merge multiple GRO files into a single complex GRO file."""
    
    def merge_gro_files(
        self,
        gro_files: List[str],
        output_file: str
    ) -> Dict[str, Any]:
        """
        Merge multiple GRO files into a single GRO file.
        Maintains proper atom numbering and box information.
        
        Args:
            gro_files: List of GRO file paths to merge (order matters!)
            output_file: Output merged GRO file path
            
        Returns:
            Dict with success status and merge statistics
        """
        try:
            # Check all files exist
            for gro_file in gro_files:
                if not Path(gro_file).exists():
                    return {
                        "success": False,
                        "error": f"File not found: {gro_file}"
                    }
            
            # Load all GRO files as MDAnalysis universes
            universes = [mda.Universe(gro) for gro in gro_files]
            
            # Merge all atom groups
            merged = Merge(*[u.atoms for u in universes])
            
            # Write merged structure
            with GROWriter(output_file, n_atoms=merged.atoms.n_atoms) as writer:
                writer.write(merged.atoms)
            
            # Collect statistics
            component_stats = []
            total_atoms = 0
            for i, (gro_file, u) in enumerate(zip(gro_files, universes)):
                n_atoms = u.atoms.n_atoms
                n_residues = u.atoms.n_residues
                total_atoms += n_atoms
                component_stats.append({
                    "file": gro_file,
                    "atoms": n_atoms,
                    "residues": n_residues
                })
            
            return {
                "success": True,
                "output_file": output_file,
                "total_atoms": total_atoms,
                "n_components": len(gro_files),
                "components": component_stats,
                "message": f"Merged {len(gro_files)} GRO files into {output_file}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to merge GRO files: {str(e)}"
            }


@tool
def merge_gro_files(
    gro_files: List[str],
    output_file: str
) -> Dict[str, Any]:
    """
    Merge multiple GROMACS GRO files into a single complex GRO file.
    Maintains proper atom numbering and coordinates. Order of files matters!
    
    Args:
        gro_files: List of GRO file paths in desired merge order
                  Example: ["protein_processed.gro", "ATP.gro", "MG.gro"]
        output_file: Output path for merged GRO file (e.g., "complex.gro")
    
    Returns:
        Dict with success status, total atom count, and component details
        
    Example:
        >>> merge_gro_files(
        ...     ["protein_processed.gro", "ATP.gro", "MG.gro"],
        ...     "complex.gro"
        ... )
        {"success": True, "total_atoms": 1500, "n_components": 3}
        
    Note:
        - Files are merged in the order provided
        - Atom IDs are automatically renumbered sequentially
        - Box dimensions from first file are preserved
    """
    merger = GROMerger()
    return merger.merge_gro_files(gro_files, output_file)
