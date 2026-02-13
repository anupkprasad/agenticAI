"""
TPR File Generator
Creates GROMACS binary run input files (.tpr) using gmx grompp
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool


@tool
def generate_tpr_file(
    mdp_file: str,
    coordinate_file: str,
    topology_file: str,
    output_tpr: Optional[str] = None,
    restraint_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    maxwarn: int = 3
) -> Dict[str, Any]:
    """
    Generate GROMACS TPR (binary run input) file using gmx grompp.
    This file contains all simulation parameters and is ready for HPC submission.
    
    Args:
        mdp_file: MDP parameter file (e.g., minim.mdp, nvt.mdp, npt.mdp, md.mdp)
        coordinate_file: Input coordinate file (.gro)
        topology_file: Input topology file (.top)
        output_tpr: Output TPR file (default: derived from mdp_file name)
        restraint_file: Reference coordinate file for position restraints (optional, typically same as coordinate_file)
        working_dir: Directory for output files and command execution
        maxwarn: Maximum number of warnings to accept (default: 3)
        
    Returns:
        Dict with success status and output file path
        
    Example:
        >>> generate_tpr_file(
        ...     mdp_file="minim.mdp",
        ...     coordinate_file="system_ions.gro",
        ...     topology_file="topol.top",
        ...     output_tpr="minim.tpr",
        ...     restraint_file="system_ions.gro"
        ... )
    """
    if working_dir:
        working_dir = Path(working_dir)
    else:
        working_dir = Path(coordinate_file).parent
    
    # Default output name: minim.mdp -> minim.tpr (relative filename)
    if not output_tpr:
        mdp_stem = Path(mdp_file).stem
        output_tpr = f"{mdp_stem}.tpr"
    
    # If restraint_file not specified, use same as coordinate_file for position restraints
    if not restraint_file:
        restraint_file = coordinate_file
    
    try:
        # All paths are relative filenames since cwd=working_dir
        grompp_cmd = [
            "gmx", "grompp",
            "-f", str(mdp_file),
            "-c", str(coordinate_file),
            "-r", str(restraint_file),
            "-p", str(topology_file),
            "-o", output_tpr,
            "-maxwarn", str(maxwarn)
        ]
        
        result = subprocess.run(
            grompp_cmd,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(working_dir)
        )
        
        if result.returncode == 0:
            return {
                "success": True,
                "output_tpr": output_tpr,
                "mdp_file": mdp_file,
                "maxwarn_used": maxwarn,
                "message": f"Successfully generated {output_tpr} from {mdp_file}"
            }
        else:
            return {
                "success": False,
                "error": f"gmx grompp failed (maxwarn={maxwarn}): {result.stderr}",
                "stderr": result.stderr,
                "maxwarn_used": maxwarn
            }
            
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "gmx grompp timed out after 120 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"TPR generation failed: {e}"
        }
