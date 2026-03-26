"""
RMSF Calculator - Root Mean Square Fluctuation analysis tool

Calculates RMSF for trajectory analysis to assess residue flexibility
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
    logger.warning("MDAnalysis not available - RMSF calculation will be limited")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


@tool
def calculate_rmsf(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_trajectory: bool = True,
    align_selection: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate RMSF (Root Mean Square Fluctuation) for a trajectory.
    
    RMSF measures per-residue flexibility. Higher RMSF indicates more flexible regions.
    Useful for identifying flexible loops, rigid cores, and binding sites.
    
    IMPORTANT: Structural alignment is performed by default to remove translational
    and rotational motions, giving meaningful RMSF values.
    
    Args:
        topology_file: Topology file (.gro, .pdb, .tpr)
        trajectory_file: Trajectory file (.xtc, .trr, .dcd)
        selection: Atom selection for RMSF calculation (default: "protein and name CA")
        output_file: Output file path for RMSF data (.dat, .csv)
        working_dir: Working directory for analysis
        align_trajectory: Whether to align trajectory before RMSF calculation (default: True)
        align_selection: Atom selection for alignment (default: same as selection)
        
    Returns:
        Dict with RMSF results and statistics
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
            logger.info(f"Calculating RMSF using MDAnalysis for {trajectory_file}")
            
            # Load universe
            u = mda.Universe(topology_file, trajectory_file)
            
            # Perform alignment if requested (CRITICAL for meaningful RMSF)
            if align_trajectory:
                from MDAnalysis.analysis import align
                
                align_sel = align_selection if align_selection else selection
                logger.info(f"Aligning trajectory using selection: {align_sel}")
                
                # Set reference to first frame
                u.trajectory[0]
                reference = u.copy()
                
                # Align trajectory in memory
                aligner = align.AlignTraj(
                    u,
                    reference,
                    select=align_sel,
                    in_memory=True
                )
                aligner.run()
                logger.info(f"Trajectory aligned: {len(u.trajectory)} frames")
            
            # Select atoms for RMSF calculation
            atoms = u.select_atoms(selection)
            
            if len(atoms) == 0:
                if working_dir:
                    os.chdir(original_dir)
                return {
                    "success": False,
                    "error": f"No atoms selected with selection: {selection}"
                }
            
            # Calculate RMSF
            R = rms.RMSF(atoms).run()
            rmsf_values = R.results.rmsf
            
            # Get residue information
            residue_ids = [atom.resid for atom in atoms]
            residue_names = [atom.resname for atom in atoms]
            
            # Calculate statistics
            mean_rmsf = float(np.mean(rmsf_values))
            std_rmsf = float(np.std(rmsf_values))
            min_rmsf = float(np.min(rmsf_values))
            max_rmsf = float(np.max(rmsf_values))
            
            # Identify most/least flexible residues
            sorted_indices = np.argsort(rmsf_values)
            most_flexible_idx = sorted_indices[-5:][::-1]  # Top 5 most flexible
            least_flexible_idx = sorted_indices[:5]  # Top 5 least flexible
            
            most_flexible = [
                {
                    "residue_id": int(residue_ids[i]),
                    "residue_name": residue_names[i],
                    "rmsf": float(rmsf_values[i])
                }
                for i in most_flexible_idx
            ]
            
            least_flexible = [
                {
                    "residue_id": int(residue_ids[i]),
                    "residue_name": residue_names[i],
                    "rmsf": float(rmsf_values[i])
                }
                for i in least_flexible_idx
            ]
            
            # Save data if requested (use filename only, already in working_dir)
            if output_file:
                output_filename = output_file
            else:
                output_filename = "rmsf.dat"
            
            with open(output_filename, 'w') as f:
                f.write("# Residue\tRMSF(Angstrom)\n")
                for res_id, rmsf_val in zip(residue_ids, rmsf_values):
                    f.write(f"{res_id}\t{rmsf_val:.4f}\n")
            
            logger.info(f"RMSF data saved to {output_filename}")
            
            # Write to analysis summary file
            if working_dir:
                try:
                    append_analysis_summary(
                        working_dir=working_dir,
                        analysis_type="RMSF",
                        statistics={
                            "n_residues": len(rmsf_values),
                            "mean_rmsf_angstrom": mean_rmsf,
                            "std_rmsf_angstrom": std_rmsf,
                            "min_rmsf_angstrom": min_rmsf,
                            "max_rmsf_angstrom": max_rmsf,
                            "most_flexible_residue": most_flexible[0]['residue_id'] if most_flexible else None,
                            "most_flexible_rmsf": most_flexible[0]['rmsf'] if most_flexible else None
                        },
                        files={
                            "topology": topology_file,
                            "trajectory": trajectory_file,
                            "data": output_file
                        },
                        metadata={
                            "selection": selection,
                            "top_5_flexible": most_flexible,
                            "top_5_rigid": least_flexible,
                            "alignment_performed": align_trajectory,
                            "align_selection": align_selection if align_selection else selection
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to write to summary file: {e}")
            
            if working_dir:
                os.chdir(original_dir)
            
            return {
                "success": True,
                "mean_rmsf": mean_rmsf,
                "std_rmsf": std_rmsf,
                "min_rmsf": min_rmsf,
                "max_rmsf": max_rmsf,
                "n_residues": len(rmsf_values),
                "most_flexible": most_flexible,
                "least_flexible": least_flexible,
                "selection": selection,
                "output_file": output_file,
                "message": f"RMSF calculation complete: mean={mean_rmsf:.2f} Å, most flexible residue at {most_flexible[0]['residue_id']}"
            }
        
        # Fallback: Use GROMACS gmx rmsf
        else:
            logger.info("Using GROMACS gmx rmsf for RMSF calculation")
            
            # Determine output file
            if not output_file:
                output_file = "rmsf.xvg"
            
            import subprocess
            
            cmd = [
                "gmx", "rmsf",
                "-s", topology_file,
                "-f", trajectory_file,
                "-o", output_file,
                "-res"  # Per-residue RMSF
            ]
            
            # Run with echo to select group (backbone or C-alpha)
            result = subprocess.run(
                cmd,
                input="3\n",  # C-alpha selection (index 3 in most cases)
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                if working_dir:
                    os.chdir(original_dir)
                return {
                    "success": False,
                    "error": f"gmx rmsf failed: {result.stderr}"
                }
            
            # Parse XVG output file
            rmsf_values = []
            residue_ids = []
            
            if os.path.exists(output_file):
                with open(output_file, 'r') as f:
                    for line in f:
                        if line.startswith('#') or line.startswith('@'):
                            continue
                        parts = line.split()
                        if len(parts) >= 2:
                            residue_ids.append(int(float(parts[0])))
                            rmsf_values.append(float(parts[1]) * 10)  # Convert nm to Angstrom
            
            if rmsf_values:
                mean_rmsf = sum(rmsf_values) / len(rmsf_values)
                std_rmsf = (sum((x - mean_rmsf)**2 for x in rmsf_values) / len(rmsf_values)) ** 0.5
                min_rmsf = min(rmsf_values)
                max_rmsf = max(rmsf_values)
                
                # Find most/least flexible
                sorted_pairs = sorted(zip(rmsf_values, residue_ids), reverse=True)
                most_flexible = [
                    {"residue_id": res_id, "rmsf": rmsf_val}
                    for rmsf_val, res_id in sorted_pairs[:5]
                ]
                least_flexible = [
                    {"residue_id": res_id, "rmsf": rmsf_val}
                    for rmsf_val, res_id in sorted_pairs[-5:]
                ]
            else:
                mean_rmsf = std_rmsf = min_rmsf = max_rmsf = 0.0
                most_flexible = []
                least_flexible = []
            
            if working_dir:
                os.chdir(original_dir)
            
            return {
                "success": True,
                "mean_rmsf": mean_rmsf,
                "std_rmsf": std_rmsf,
                "min_rmsf": min_rmsf,
                "max_rmsf": max_rmsf,
                "n_residues": len(rmsf_values),
                "most_flexible": most_flexible,
                "least_flexible": least_flexible,
                "selection": "C-alpha (GROMACS default)",
                "output_file": output_file,
                "message": f"RMSF calculation complete using GROMACS: mean={mean_rmsf:.2f} Å"
            }
        
    except Exception as e:
        logger.exception(f"RMSF calculation failed: {e}")
        if working_dir and 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"RMSF calculation failed: {str(e)}"
        }
