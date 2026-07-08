"""
RMSD Calculator - Root Mean Square Deviation analysis tool

Calculates RMSD for trajectory analysis to assess structural stability
"""
import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from langchain.tools import tool
from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import rms
    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    logger.warning("MDAnalysis not available - RMSD calculation will be limited")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def compute_rmsd_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    reference_frame: int = 0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_before_rmsd: bool = True,
    pre_aligned: bool = False,
) -> Dict[str, Any]:
    """Compute RMSD using a pre-loaded Universe (optionally pre-aligned)."""
    if not HAS_MDA or not HAS_NUMPY:
        return {"success": False, "error": "MDAnalysis and numpy are required for RMSD"}

    if pre_aligned:
        align_before_rmsd = False

    R = rms.RMSD(
        u,
        select=selection,
        ref_frame=reference_frame,
        groupselections=[selection] if not align_before_rmsd else None,
    )
    R.run()

    rmsd_data = R.results.rmsd
    times = rmsd_data[:, 1]
    rmsd_values = rmsd_data[:, 2]

    mean_rmsd = float(np.mean(rmsd_values))
    std_rmsd = float(np.std(rmsd_values))
    min_rmsd = float(np.min(rmsd_values))
    max_rmsd = float(np.max(rmsd_values))

    output_filename = output_file or "rmsd.dat"
    with open(output_filename, "w") as f:
        f.write("# Time(ns)\tRMSD(Angstrom)\n")
        for t, r in zip(times, rmsd_values):
            f.write(f"{t/1000.0:.4f}\t{r:.4f}\n")

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="RMSD",
                statistics={
                    "n_frames": len(rmsd_values),
                    "mean_rmsd_angstrom": mean_rmsd,
                    "std_rmsd_angstrom": std_rmsd,
                    "min_rmsd_angstrom": min_rmsd,
                    "max_rmsd_angstrom": max_rmsd,
                },
                files={
                    "topology": topology_file,
                    "trajectory": trajectory_file,
                    "data": output_filename,
                },
                metadata={
                    "selection": selection,
                    "reference_frame": reference_frame,
                    "alignment_performed": align_before_rmsd,
                    "pre_aligned_universe": pre_aligned,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to write to summary file: {e}")

    return {
        "success": True,
        "mean_rmsd": mean_rmsd,
        "std_rmsd": std_rmsd,
        "min_rmsd": min_rmsd,
        "max_rmsd": max_rmsd,
        "n_frames": len(rmsd_values),
        "selection": selection,
        "output_file": output_filename,
        "message": f"RMSD calculation complete: mean={mean_rmsd:.2f} Å, std={std_rmsd:.2f} Å",
    }


@tool
def calculate_rmsd(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    reference_frame: int = 0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_before_rmsd: bool = True
) -> Dict[str, Any]:
    """
    Calculate RMSD (Root Mean Square Deviation) for a trajectory.
    
    RMSD measures structural deviation over time, indicating stability.
    Lower RMSD values suggest stable structures.
    
    NOTE: The RMSD calculation in MDAnalysis automatically performs alignment
    before computing RMSD. Set align_before_rmsd=False to disable this.
    
    Args:
        topology_file: Topology file (.gro, .pdb, .tpr) - full path
        trajectory_file: Trajectory file (.xtc, .trr, .dcd) - full path
        selection: Atom selection for RMSD calculation (default: "protein and name CA")
        reference_frame: Reference frame number (default: 0 - first frame)
        output_file: Output filename only (default: "rmsd.dat") - file saved in working_dir
        working_dir: Working directory for analysis (files will be written here)
        align_before_rmsd: Whether to align before RMSD calculation (default: True)
        
    Returns:
        Dict with RMSD results and statistics
    
    Output file format (tab-separated, # comment header):
        # Time(ns)\tRMSD(Angstrom)
        0.0000\t0.0000
        0.1000\t0.9425
        ...
    """
    try:
        # Setup working directory
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)
        
        # Validate input files
        if not os.path.exists(topology_file):
            return {
                "success": False,
                "error": f"Topology file not found: {topology_file}"
            }
        
        if not os.path.exists(trajectory_file):
            return {
                "success": False,
                "error": f"Trajectory file not found: {trajectory_file}"
            }
        
        # Use MDAnalysis if available
        if HAS_MDA and HAS_NUMPY:
            logger.info(f"Calculating RMSD using MDAnalysis for {trajectory_file}")
            result = compute_rmsd_from_universe(
                mda.Universe(topology_file, trajectory_file),
                topology_file=topology_file,
                trajectory_file=trajectory_file,
                selection=selection,
                reference_frame=reference_frame,
                output_file=output_file,
                working_dir=working_dir,
                align_before_rmsd=align_before_rmsd,
            )
            if working_dir:
                os.chdir(original_dir)
            return result
        
        # Fallback: Use GROMACS gmx rms
        else:
            logger.info("Using GROMACS gmx rms for RMSD calculation")
            
            # Determine output file
            if not output_file:
                output_file = "rmsd.xvg"
            
            # Create index file for selection if needed
            import subprocess
            
            # Simple approach: assume backbone selection (index 4 in most cases)
            # More sophisticated: create custom index file
            
            cmd = [
                "gmx", "rms",
                "-s", topology_file,
                "-f", trajectory_file,
                "-o", output_file,
                "-tu", "ps"
            ]
            
            # Run with echo to select groups (backbone vs backbone)
            result = subprocess.run(
                cmd,
                input="4\n4\n",  # Backbone selection
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                if working_dir:
                    os.chdir(original_dir)
                return {
                    "success": False,
                    "error": f"gmx rms failed: {result.stderr}"
                }
            
            # Parse XVG output file
            rmsd_values = []
            times = []
            
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    for line in f:
                        if line.startswith('#') or line.startswith('@'):
                            continue
                        parts = line.split()
                        if len(parts) >= 2:
                            times.append(float(parts[0]))
                            rmsd_values.append(float(parts[1]) * 10)  # Convert nm to Angstrom
            
            if rmsd_values:
                mean_rmsd = sum(rmsd_values) / len(rmsd_values)
                std_rmsd = (sum((x - mean_rmsd)**2 for x in rmsd_values) / len(rmsd_values)) ** 0.5
                min_rmsd = min(rmsd_values)
                max_rmsd = max(rmsd_values)
            else:
                mean_rmsd = std_rmsd = min_rmsd = max_rmsd = 0.0
            
            if working_dir:
                os.chdir(original_dir)
            
            return {
                "success": True,
                "mean_rmsd": mean_rmsd,
                "std_rmsd": std_rmsd,
                "min_rmsd": min_rmsd,
                "max_rmsd": max_rmsd,
                "n_frames": len(rmsd_values),
                "selection": "backbone (GROMACS default)",
                "output_file": output_file,
                "message": f"RMSD calculation complete using GROMACS: mean={mean_rmsd:.2f} Å"
            }
        
    except Exception as e:
        logger.exception(f"RMSD calculation failed: {e}")
        if working_dir and 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"RMSD calculation failed: {str(e)}"
        }
