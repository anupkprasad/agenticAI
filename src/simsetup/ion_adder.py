"""
Ion Addition Tool
Adds ions to neutralize system and set ionic strength using gmx genion
"""
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional


def add_ions(
    coordinate_file: str,
    topology_file: str,
    mdp_file: str,
    positive_ion: str = "NA",
    negative_ion: str = "CL",
    neutral: bool = True,
    concentration: float = 0.15,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add ions to system using gmx genion for neutralization and ionic strength.
    
    Args:
        coordinate_file: Input solvated coordinate file (.gro)
        topology_file: Input topology file (.top)
        mdp_file: MDP file for grompp (ions.mdp)
        positive_ion: Positive ion type (NA, K, etc.)
        negative_ion: Negative ion type (CL, etc.)
        neutral: Neutralize system charge (default: True)
        concentration: Ionic concentration in Molar (default: 0.15, physiological)
        output_file: Output coordinate file with ions
        working_dir: Directory for output files and command execution
        
    Returns:
        Dict with success, output_file, and ion counts
    """
    if working_dir:
        working_dir = Path(working_dir)
    else:
        working_dir = Path(coordinate_file).parent
    
    if not output_file:
        base = Path(coordinate_file).stem
        output_file = f"{base}_ions.gro"  # Just filename - working_dir handles location
    
    # Use relative path since we run with cwd=working_dir
    tpr_file = "ions.tpr"
    maxwarn = 3  # Allow up to 3 warnings (increased for robustness)
    
    try:
        # Step 1: Create TPR file with grompp
        # All paths are relative filenames since cwd=working_dir
        grompp_cmd = [
            "gmx", "grompp",
            "-f", str(mdp_file),
            "-c", str(coordinate_file),
            "-p", str(topology_file),
            "-o", tpr_file,
            "-maxwarn", str(maxwarn)
        ]
        
        grompp_result = subprocess.run(
            grompp_cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=str(working_dir)
        )
        
        if grompp_result.returncode != 0:
            return {
                "success": False,
                "error": f"grompp failed (maxwarn={maxwarn}): {grompp_result.stderr}",
                "maxwarn_used": maxwarn
            }
        
        # Step 2: Add ions with genion
        genion_cmd = [
            "gmx", "genion",
            "-s", tpr_file,
            "-o", str(output_file),
            "-p", str(topology_file),
            "-pname", positive_ion,
            "-nname", negative_ion
        ]
        
        if neutral:
            genion_cmd.append("-neutral")
        if concentration > 0:
            genion_cmd.extend(["-conc", str(concentration)])
        
        # Pipe "SOL" to select solvent for replacement
        genion_result = subprocess.run(
            genion_cmd,
            input="SOL\n",
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(working_dir)
        )
        
        if genion_result.returncode == 0:
            # Parse ion counts from output
            positive_count = 0
            negative_count = 0
            
            for line in genion_result.stdout.split('\n'):
                if positive_ion in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == positive_ion and i+1 < len(parts):
                            if parts[i+1].isdigit():
                                positive_count = int(parts[i+1])
                elif negative_ion in line:
                    parts = line.split()
                    for i, part in enumerate(parts):
                        if part == negative_ion and i+1 < len(parts):
                            if parts[i+1].isdigit():
                                negative_count = int(parts[i+1])
            
            return {
                "success": True,
                "output_file": output_file,
                "positive_ion": positive_ion,
                "negative_ion": negative_ion,
                "positive_ion_count": positive_count,
                "negative_ion_count": negative_count,
                "concentration": concentration,
                "maxwarn_used": maxwarn,
                "message": f"Ions added: {positive_count} {positive_ion}, {negative_count} {negative_ion} (concentration: {concentration} M, maxwarn: {maxwarn})"
            }
        else:
            return {
                "success": False,
                "error": f"gmx genion failed: {genion_result.stderr}"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"Ion addition failed: {e}"
        }
