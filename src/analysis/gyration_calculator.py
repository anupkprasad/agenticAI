"""
Radius of Gyration Calculator - Compactness analysis tool

Calculates radius of gyration (Rg) to measure protein compactness over time
"""
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from langchain.tools import tool
from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import MDAnalysis as mda
    HAS_MDA = True
except ImportError:
    HAS_MDA = False

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def finalize_rg_result(
    times: list,
    rg_values: list,
    *,
    selection: str,
    output_file: Optional[str],
    topology_file: str,
    trajectory_file: str,
    working_dir: Optional[str],
    align_before_rg: bool = False,
) -> Dict[str, Any]:
    """Write Rg outputs and summary from collected per-frame values."""
    if not rg_values:
        return {"success": False, "error": "No Rg values collected"}

    rg_arr = np.array(rg_values)
    times_arr = np.array(times)
    mean_rg = float(np.mean(rg_arr))
    std_rg = float(np.std(rg_arr))
    min_rg = float(np.min(rg_arr))
    max_rg = float(np.max(rg_arr))

    output_filename = output_file or "rg.dat"
    with open(output_filename, "w") as f:
        f.write("# Time(ps)\tRg(Angstrom)\n")
        for t, rg in zip(times_arr, rg_arr):
            f.write(f"{t:.4f}\t{rg:.4f}\n")

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Radius_of_Gyration",
                statistics={
                    "n_frames": len(rg_arr),
                    "mean_rg_angstrom": mean_rg,
                    "std_rg_angstrom": std_rg,
                    "min_rg_angstrom": min_rg,
                    "max_rg_angstrom": max_rg,
                },
                files={"topology": topology_file, "trajectory": trajectory_file, "data": output_filename},
                metadata={"selection": selection, "align_before_rg": align_before_rg},
            )
        except Exception as e:
            logger.warning(f"Failed to write to summary file: {e}")

    return {
        "success": True,
        "mean_rg": mean_rg,
        "std_rg": std_rg,
        "min_rg": min_rg,
        "max_rg": max_rg,
        "n_frames": len(rg_arr),
        "selection": selection,
        "output_file": output_filename,
        "message": f"Rg calculation complete: mean={mean_rg:.2f} Å, std={std_rg:.2f} Å",
    }


def compute_rg_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_before_rg: bool = False,
) -> Dict[str, Any]:
    """Compute radius of gyration from a pre-loaded Universe."""
    if not HAS_MDA or not HAS_NUMPY:
        return {"success": False, "error": "MDAnalysis and numpy are required for Rg"}

    atoms = u.select_atoms(selection)
    if len(atoms) == 0:
        return {"success": False, "error": f"No atoms selected with selection: {selection}"}

    rg_values = []
    times = []
    for ts in u.trajectory:
        rg_values.append(float(atoms.radius_of_gyration()))
        times.append(float(ts.time))

    return finalize_rg_result(
        times,
        rg_values,
        selection=selection,
        output_file=output_file,
        topology_file=topology_file,
        trajectory_file=trajectory_file,
        working_dir=working_dir,
        align_before_rg=align_before_rg,
    )


@tool
def calculate_radius_of_gyration(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_before_rg: bool = False,
    align_selection: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate radius of gyration (Rg) for a trajectory.
    
    Rg measures the compactness of a protein structure. Changes in Rg
    indicate folding/unfolding events or conformational changes.

    Set ``align_before_rg=True`` to compute Rg on structurally aligned coordinates
    (same pass as RMSD/RMSF). Default ``False`` preserves diffusion in raw coords.
    
    Args:
        topology_file: Topology file (.gro, .pdb, .tpr) - full path
        trajectory_file: Trajectory file (.xtc, .trr, .dcd) - full path  
        selection: Atom selection for Rg calculation (default: "protein")
        output_file: Output filename only (default: "rg.dat") - file saved in working_dir
        working_dir: Working directory for analysis (files will be written here)
        align_before_rg: Superpose trajectory before Rg (default: False)
        align_selection: Atoms used for alignment when align_before_rg=True
            (default: "protein and name CA")
    Returns:
        Dict with Rg results and statistics
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
            logger.info(f"Calculating Rg using MDAnalysis for {trajectory_file}")
            u = mda.Universe(topology_file, trajectory_file)
            if align_before_rg:
                from MDAnalysis.analysis import align

                align_sel = align_selection or "protein and name CA"
                u.trajectory[0]
                reference = u.copy()
                align.AlignTraj(u, reference, select=align_sel, in_memory=True).run()
            result = compute_rg_from_universe(
                u,
                topology_file=topology_file,
                trajectory_file=trajectory_file,
                selection=selection,
                output_file=output_file,
                working_dir=working_dir,
                align_before_rg=align_before_rg,
            )
            if working_dir:
                os.chdir(original_dir)
            return result
        
        # Fallback: Use GROMACS gmx gyrate
        else:
            logger.info("Using GROMACS gmx gyrate for Rg calculation")
            
            # Determine output file
            if not output_file:
                output_file = "gyrate.xvg"
            
            import subprocess
            
            cmd = [
                "gmx", "gyrate",
                "-s", topology_file,
                "-f", trajectory_file,
                "-o", output_file
            ]
            
            # Run with echo to select group (protein)
            result = subprocess.run(
                cmd,
                input="1\n",  # Protein selection
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                if working_dir:
                    os.chdir(original_dir)
                return {
                    "success": False,
                    "error": f"gmx gyrate failed: {result.stderr}"
                }
            
            # Parse XVG output file
            rg_values = []
            times = []
            
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    for line in f:
                        if line.startswith('#') or line.startswith('@'):
                            continue
                        parts = line.split()
                        if len(parts) >= 2:
                            times.append(float(parts[0]))
                            rg_values.append(float(parts[1]) * 10)  # Convert nm to Angstrom
            
            if rg_values:
                mean_rg = sum(rg_values) / len(rg_values)
                std_rg = (sum((x - mean_rg)**2 for x in rg_values) / len(rg_values)) ** 0.5
                min_rg = min(rg_values)
                max_rg = max(rg_values)
            else:
                mean_rg = std_rg = min_rg = max_rg = 0.0
            
            if working_dir:
                os.chdir(original_dir)
            
            return {
                "success": True,
                "mean_rg": mean_rg,
                "std_rg": std_rg,
                "min_rg": min_rg,
                "max_rg": max_rg,
                "n_frames": len(rg_values),
                "selection": "protein (GROMACS default)",
                "output_file": output_file,
                "message": f"Rg calculation complete using GROMACS: mean={mean_rg:.2f} Å"
            }
        
    except Exception as e:
        logger.exception(f"Rg calculation failed: {e}")
        if working_dir and 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"Rg calculation failed: {str(e)}"
        }
