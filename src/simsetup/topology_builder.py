"""
Topology Builder Tool
Generates GROMACS topology files using gmx pdb2gmx
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def build_topology(
    pdb_file: str,
    force_field: str = "amber99sb-ildn",
    water_model: str = "tip3p",
    output_file: Optional[str] = None,
    topology_file: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate GROMACS topology and coordinate files using pdb2gmx.
    
    Args:
        pdb_file: Input PDB file path
        force_field: Force field to use (default: amber99sb-ildn)
        water_model: Water model to use (default: tip3p)
        output_file: Output coordinate file (.gro)
        topology_file: Output topology file (.top)
        working_dir: Directory for output files and command execution
        
    Returns:
        Dict with success status, output files, and force field info
    """
    if working_dir:
        working_dir = Path(working_dir)
    else:
        working_dir = Path(pdb_file).parent
    
    if not output_file:
        output_file = str(working_dir / "processed.gro")
    if not topology_file:
        topology_file = str(working_dir / "topol.top")
    
    # Sanitize water_model: reject "none"/empty → default to tip3p
    valid_water_models = {"tip3p", "tip4p", "tip5p", "spc", "spc216", "spce"}
    if not water_model or water_model.lower().strip() in ("none", "", "vacuum"):
        water_model = "tip3p"
    
    try:
        # Run gmx pdb2gmx
        cmd = [
            "gmx", "pdb2gmx",
            "-f", str(pdb_file),
            "-o", str(output_file),
            "-p", str(topology_file),
            "-ff", force_field,
            "-water", water_model,
            "-ignh"  # Ignore hydrogens in input
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
                "output_file": output_file,
                "topology_file": topology_file,
                "force_field": force_field,
                "water_model": water_model,
                "message": "Topology generated using gmx pdb2gmx"
            }
        else:
            return {
                "success": False,
                "error": f"GROMACS pdb2gmx failed: {result.stderr}",
                "stdout": result.stdout
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Topology building failed: {e}"
        }
