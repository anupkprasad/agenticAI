"""
AMBER to GROMACS Converter Tool
Converts AMBER format topology/coordinates to GROMACS format
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool


@tool
def convert_amber_to_gromacs(
    prmtop_file: str,
    inpcrd_file: str,
    output_top: Optional[str] = None,
    output_gro: Optional[str] = None
) -> Dict[str, Any]:
    """
    Convert AMBER prmtop/inpcrd files to GROMACS top/gro format.
    
    Args:
        prmtop_file: AMBER topology file (.prmtop)
        inpcrd_file: AMBER coordinate file (.inpcrd)
        output_top: Output GROMACS topology file (.top)
        output_gro: Output GROMACS coordinate file (.gro)
        
    Returns:
        Dict with success status and converted file paths
    """
    working_dir = Path(prmtop_file).parent
    
    if not output_top:
        output_top = str(working_dir / "converted.top")
    if not output_gro:
        output_gro = str(working_dir / "converted.gro")
    
    try:
        # Using ACPYPE or ParmEd for conversion
        # Try ACPYPE first
        cmd = [
            "acpype",
            "-p", str(prmtop_file),
            "-x", str(inpcrd_file),
            "-o", "gmx"
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(working_dir)
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "topology_file": output_top,
                "coordinate_file": output_gro,
                "method": "acpype",
                "message": "AMBER files converted to GROMACS format"
            }
        else:
            # Try ParmEd as fallback
            try:
                import parmed as pmd
                
                # Load AMBER files
                amber_system = pmd.load_file(str(prmtop_file), str(inpcrd_file))
                
                # Save as GROMACS
                amber_system.save(str(output_top))
                amber_system.save(str(output_gro))
                
                return {
                    "success": True,
                    "topology_file": output_top,
                    "coordinate_file": output_gro,
                    "method": "parmed",
                    "message": "AMBER files converted using ParmEd"
                }
            except Exception as parmed_error:
                return {
                    "success": False,
                    "error": f"Both ACPYPE and ParmEd failed. ACPYPE: {result.stderr}, ParmEd: {parmed_error}"
                }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"AMBER to GROMACS conversion failed: {e}"
        }
