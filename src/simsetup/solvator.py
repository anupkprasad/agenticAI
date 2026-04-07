"""
Solvation Tool
Adds water molecules to simulation box using gmx solvate
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def solvate_system(
    coordinate_file: str,
    topology_file: str,
    water_model: str = "spc216",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add water molecules to simulation system using gmx solvate.
    
    CRITICAL: GMX solvate modifies the topology file IN-PLACE via the -p flag.
    Always pass the same topology file (typically topol.top) that was created by build_topology.
    
    Args:
        coordinate_file: Input coordinate file with box (.gro)
        topology_file: Topology file to update IN-PLACE (typically topol.top)
        water_model: Water model - 'spc216' (default), 'spc', 'tip4p', 'tip5p'
                     Note: tip3p not supported by gmx solvate, use default or spc216
                     If default (spc216) or not in valid list, -cs flag is omitted
        output_file: Output solvated coordinate file
        working_dir: Directory for output files and command execution
        
    Returns:
        Dict with success status, output files, and water count
    """
    if working_dir:
        working_dir = Path(working_dir)
    else:
        working_dir = Path(coordinate_file).parent
    
    if not output_file:
        base = Path(coordinate_file).stem
        output_file = str(working_dir / f"{base}_solv.gro")
    
    try:
        # Build command - only add -cs flag if water_model specified and not default
        cmd = [
            "gmx", "solvate",
            "-cp", str(coordinate_file),
            "-p", str(topology_file),
            "-o", str(output_file)
        ]
        
        # Only add -cs flag if water model explicitly provided and is a valid solvent config
        # Common valid configs: spc216, spc, tip4p, tip5p (but NOT tip3p which doesn't have .gro)
        # Most users can just omit this flag and use GROMACS default
        if water_model and water_model != "spc216" and water_model in ["spc", "tip4p", "tip5p"]:
            cmd.insert(4, "-cs")
            cmd.insert(5, water_model)
        
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
                "topology_file": topology_file,  # Same file, modified in-place by gmx
                "water_model": water_model,
                "water_molecules_added": water_count,
                "message": f"System solvated with {water_count} water molecules (topology updated in-place)"
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
