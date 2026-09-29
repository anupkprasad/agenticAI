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


def compute_rmsf_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_trajectory: bool = True,
    align_selection: Optional[str] = None,
    skip_align: bool = False,
) -> Dict[str, Any]:
    """Compute RMSF from a pre-loaded Universe."""
    if not HAS_MDA or not HAS_NUMPY:
        return {"success": False, "error": "MDAnalysis and numpy are required for RMSF"}

    if align_trajectory and not skip_align:
        from MDAnalysis.analysis import align

        align_sel = align_selection if align_selection else selection
        u.trajectory[0]
        reference = u.copy()
        align.AlignTraj(u, reference, select=align_sel, in_memory=True).run()

    atoms = u.select_atoms(selection)
    if len(atoms) == 0:
        return {"success": False, "error": f"No atoms selected with selection: {selection}"}

    R = rms.RMSF(atoms).run()
    rmsf_values = R.results.rmsf
    residue_ids = [atom.resid for atom in atoms]
    residue_names = [atom.resname for atom in atoms]

    mean_rmsf = float(np.mean(rmsf_values))
    std_rmsf = float(np.std(rmsf_values))
    min_rmsf = float(np.min(rmsf_values))
    max_rmsf = float(np.max(rmsf_values))

    sorted_indices = np.argsort(rmsf_values)
    most_flexible_idx = sorted_indices[-5:][::-1]
    least_flexible_idx = sorted_indices[:5]

    most_flexible = [
        {"residue_id": int(residue_ids[i]), "residue_name": residue_names[i], "rmsf": float(rmsf_values[i])}
        for i in most_flexible_idx
    ]
    least_flexible = [
        {"residue_id": int(residue_ids[i]), "residue_name": residue_names[i], "rmsf": float(rmsf_values[i])}
        for i in least_flexible_idx
    ]

    output_filename = output_file or "rmsf.dat"
    with open(output_filename, "w") as f:
        f.write("# Residue\tRMSF(Angstrom)\n")
        for res_id, rmsf_val in zip(residue_ids, rmsf_values):
            f.write(f"{res_id}\t{rmsf_val:.4f}\n")

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
                    "most_flexible_residue": most_flexible[0]["residue_id"] if most_flexible else None,
                    "most_flexible_rmsf": most_flexible[0]["rmsf"] if most_flexible else None,
                },
                files={"topology": topology_file, "trajectory": trajectory_file, "data": output_filename},
                metadata={
                    "selection": selection,
                    "top_5_flexible": most_flexible,
                    "top_5_rigid": least_flexible,
                    "alignment_performed": align_trajectory and not skip_align,
                    "align_selection": align_selection if align_selection else selection,
                    "pre_aligned_universe": skip_align,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to write to summary file: {e}")

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
        "output_file": output_filename,
        "message": (
            f"RMSF calculation complete: mean={mean_rmsf:.2f} Å, "
            f"most flexible residue at {most_flexible[0]['residue_id'] if most_flexible else 'n/a'}"
        ),
    }


@tool
def calculate_rmsf(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_trajectory: bool = True,
    align_selection: Optional[str] = None,
    selection_from_file: Optional[str] = None,
    selection_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Calculate per-residue RMSF for **one** trajectory (local, non-mapped).

    RMSF measures per-residue flexibility after optional alignment.

    **Family / comparative MD:** do **not** use this for cross-system feature
    tables. Prefer ``calculate_consensus_rmsf_features``, which writes
    MSA-mapped scalars (``consensus_rmsf_mean_A`` / ``_std_A``) that are
    comparable across proteins. Local ``rmsf.dat`` values are not interchangeable
    with consensus RMSF and will change clustering scale.

    Use this tool for single-system inspection or when the user explicitly asks
    for whole-protein (non-mapped) RMSF.
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
            from .proximity_analyzer import apply_selection_from_files

            resolved = apply_selection_from_files(
                {
                    "selection": selection,
                    "selection_from_file": selection_from_file,
                    "selection_key": selection_key,
                },
                working_dir=working_dir,
            )
            selection = resolved.get("selection", selection)
            logger.info(f"Calculating RMSF using MDAnalysis for {trajectory_file}")
            result = compute_rmsf_from_universe(
                mda.Universe(topology_file, trajectory_file),
                topology_file=topology_file,
                trajectory_file=trajectory_file,
                selection=selection,
                output_file=output_file,
                working_dir=working_dir,
                align_trajectory=align_trajectory,
                align_selection=align_selection,
            )
            if working_dir:
                os.chdir(original_dir)
            return result
        
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
