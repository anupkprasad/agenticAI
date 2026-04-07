"""
Simulation Box Builder Tool
Defines simulation box using gmx editconf
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def build_simulation_box(
    coordinate_file: str,
    box_type: str = "cubic",
    box_distance: float = 1.0,
    output_file: Optional[str] = None,
    center_molecule: bool = True,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Define simulation box around molecule using gmx editconf.
    
    Args:
        coordinate_file: Input coordinate file (.gro or .pdb)
        box_type: Box type - 'cubic', 'dodecahedron', 'octahedron'
        box_distance: Distance from molecule to box edge (nm)
        output_file: Output coordinate file path
        center_molecule: Center molecule in box
        working_dir: Directory for output files and command execution
        
    Returns:
        Dict with success, output_file, box info
    """
    if working_dir:
        working_dir = Path(working_dir)
    else:
        working_dir = Path(coordinate_file).parent

    
    if not output_file:
        base = Path(coordinate_file).stem
        output_file = str(working_dir / f"{base}_box.gro")
    
    try:
        cmd = [
            "gmx", "editconf",
            "-f", str(coordinate_file),
            "-o", str(output_file),
            "-bt", box_type,
            "-d", str(box_distance)
        ]
        
        if center_molecule:
            cmd.extend(["-c"])  # Center molecule in box
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(working_dir)
        )
        
        if result.returncode == 0:
            # Parse box dimensions from output
            box_dims = None
            for line in result.stdout.split('\n'):
                if 'box vectors' in line.lower():
                    box_dims = line.strip()
                    break
            
            return {
                "success": True,
                "output_file": output_file,
                "box_type": box_type,
                "box_distance": box_distance,
                "box_dimensions": box_dims,
                "message": f"Simulation box created: {box_type}, distance {box_distance} nm"
            }
        else:
            return {
                "success": False,
                "error": f"gmx editconf failed: {result.stderr}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Box building failed: {e}"
        }
