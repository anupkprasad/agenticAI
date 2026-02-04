"""
Solvation Tool
Adds water molecules to simulation box using gmx solvate
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool


@tool
def solvate_system(
    coordinate_file: str,
    topology_file: str,
    water_model: str = "spc216",
    output_file: Optional[str] = None,
    output_topology: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add water molecules to simulation system using gmx solvate.
    
    Args:
        coordinate_file: Input coordinate file with box (.gro)
        topology_file: Input topology file (.top)
        water_model: Water model - 'spc216', 'tip3p', 'tip4p'
        output_file: Output solvated coordinate file
        output_topology: Output updated topology file
        
    Returns:
        Dict with success status, output files, and water count
    """
    working_dir = Path(coordinate_file).parent
    
    if not output_file:
        base = Path(coordinate_file).stem
        output_file = str(working_dir / f"{base}_solv.gro")
    if not output_topology:
        output_topology = str(working_dir / "topol_solv.top")
    
    try:
        cmd = [
            "gmx", "solvate",
            "-cp", str(coordinate_file),
            "-cs", water_model,
            "-p", str(topology_file),
            "-o", str(output_file)
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(working_dir)
        )
        
        if result.returncode == 0:
            # Parse water count from output
            water_count = 0
            for line in result.stdout.split('\n'):
                if 'SOL' in line or 'water' in line.lower():
                    # Extract number from line
                    parts = line.split()
                    for part in parts:
                        if part.isdigit():
                            water_count = int(part)
                            break
            
            return {
                "success": True,
                "output_file": output_file,
                "topology_file": output_topology,
                "water_model": water_model,
                "water_molecules_added": water_count,
                "message": f"System solvated with {water_count} water molecules"
            }
        else:
            return {
                "success": False,
                "error": f"gmx solvate failed: {result.stderr}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Solvation failed: {e}"
        }
