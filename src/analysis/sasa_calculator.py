"""
SASA Calculator - Solvent Accessible Surface Area analysis tool using GROMACS

Calculates per-frame SASA for trajectory analysis using GROMACS gmx sasa command
"""
import os
import subprocess
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from langchain.tools import tool
from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import numpy as np
    import pandas as pd
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False
    logger.warning("numpy and pandas not available - SASA calculation will be limited")


@tool
def calculate_sasa(
    topology_file: str,
    trajectory_file: str,
    selection: str = "Protein",
    probe_radius: float = 0.14,
    output_csv: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Calculate SASA (Solvent Accessible Surface Area) using GROMACS gmx sasa.
    
    SASA measures the surface area of a biomolecule that is accessible to a 
    solvent (typically water). This is useful for understanding protein folding,
    binding interfaces, and conformational changes.
    
    Args:
        topology_file: Topology file (.tpr preferred, or .gro with warnings) - full path
        trajectory_file: Trajectory file (.xtc, .trr) - full path
        selection: GROMACS selection (default: "Protein"). Can use: "Protein", "Protein-H", 
                   custom index groups, or combinations like "Protein_LIG" for protein+ligand
        probe_radius: Probe radius in nm (default: 0.14 nm = 1.4 Å for water)
        output_csv: Output CSV filename only (default: "sasa.csv") - file saved in working_dir
        working_dir: Working directory for analysis (files will be written here)
        
    Returns:
        Dict with SASA results and statistics
    """
    original_dir = None
    temp_files = []
    
    try:
        # Setup working directory
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)
        
        # Check dependencies
        if not HAS_NUMPY:
            error_msg = "numpy and pandas are required for SASA calculation"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "tool": "calculate_sasa"
            }
        
        # Check if gmx is available
        gmx_cmd = None
        for cmd in ['gmx', 'gmx_mpi']:
            try:
                result = subprocess.run([cmd, '--version'], capture_output=True, timeout=5)
                if result.returncode == 0:
                    gmx_cmd = cmd
                    break
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        
        if gmx_cmd is None:
            error_msg = "GROMACS (gmx) not found in PATH. Please ensure GROMACS is installed and available."
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "tool": "calculate_sasa"
            }
        
        logger.info(f"Using GROMACS command: {gmx_cmd}")
        
        # Resolve file paths
        def resolve_file_path(file_path: str, file_type: str) -> str:
            """Resolve file path, checking multiple locations"""
            if os.path.isabs(file_path) and os.path.exists(file_path):
                return file_path
            if os.path.exists(file_path):
                return os.path.abspath(file_path)
            if original_dir:
                orig_path = os.path.join(original_dir, file_path)
                if os.path.exists(orig_path):
                    return orig_path
            parent_path = os.path.join("..", file_path)
            if os.path.exists(parent_path):
                return os.path.abspath(parent_path)
            raise FileNotFoundError(f"{file_type} file not found: {file_path}")
        
        topology_file = resolve_file_path(topology_file, "Topology")
        trajectory_file = resolve_file_path(trajectory_file, "Trajectory")
        
        logger.info(f"Topology: {topology_file}")
        logger.info(f"Trajectory: {trajectory_file}")
        logger.info(f"Selection: {selection}")
        logger.info(f"Probe radius: {probe_radius} nm")
        
        # Prepare output files
        sasa_xvg = "sasa_output.xvg"
        temp_files.append(sasa_xvg)
        
        # Convert selection format if needed
        # Handle common cases: "protein", "Protein", "protein-ligand" -> use as-is for GROMACS
        gmx_selection = selection.strip()
        
        # Build gmx sasa command
        # gmx sasa -f trajectory -s topology -o output.xvg -surface selection -output selection
        cmd = [
            gmx_cmd, 'sasa',
            '-f', trajectory_file,
            '-s', topology_file,
            '-o', sasa_xvg,
            '-probe', str(probe_radius)
        ]
        
        logger.info(f"Running GROMACS SASA calculation...")
        logger.debug(f"Command: {' '.join(cmd)}")
        
        # Prepare input for group selection
        # For gmx sasa, we need to provide the group selection via stdin
        # Format: "group_name\ngroup_name\n" (surface group and output group)
        selection_input = f"{gmx_selection}\n{gmx_selection}\n"
        
        try:
            result = subprocess.run(
                cmd,
                input=selection_input,
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )
            
            if result.returncode != 0:
                logger.error(f"GROMACS stderr: {result.stderr}")
                return {
                    "success": False,
                    "error": f"gmx sasa failed: {result.stderr[:500]}",
                    "tool": "calculate_sasa"
                }
            
            logger.info("GROMACS SASA calculation completed")
            
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "SASA calculation timed out (>5 minutes)",
                "tool": "calculate_sasa"
            }
        
        # Parse .xvg file
        if not os.path.exists(sasa_xvg):
            return {
                "success": False,
                "error": f"SASA output file not created: {sasa_xvg}",
                "tool": "calculate_sasa"
            }
        
        times = []
        sasa_values = []
        
        with open(sasa_xvg, 'r') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if line.startswith('#') or line.startswith('@') or not line:
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        times.append(float(parts[0]))
                        sasa_values.append(float(parts[1]))
                    except ValueError:
                        continue
        
        if not sasa_values:
            return {
                "success": False,
                "error": "No SASA data found in output file",
                "tool": "calculate_sasa"
            }
        
        times = np.array(times)
        sasa_values = np.array(sasa_values)
        frames = np.arange(len(sasa_values))
        
        # Calculate statistics
        mean_sasa = float(np.mean(sasa_values))
        std_sasa = float(np.std(sasa_values))
        min_sasa = float(np.min(sasa_values))
        max_sasa = float(np.max(sasa_values))
        
        logger.info(f"SASA Statistics:")
        logger.info(f"  Mean: {mean_sasa:.2f} nm²")
        logger.info(f"  Std:  {std_sasa:.2f} nm²")
        logger.info(f"  Min:  {min_sasa:.2f} nm²")
        logger.info(f"  Max:  {max_sasa:.2f} nm²")
        
        # Save to CSV (use filename only, already in working_dir)
        csv_filename = output_csv if output_csv else "sasa.csv"
        df = pd.DataFrame({
            'frame': frames,
            'time': times,
            'sasa': sasa_values
        })
        df.to_csv(csv_filename, index=False)
        logger.info(f"SASA data saved to: {csv_filename}")
        
        # Write to analysis summary file
        if working_dir:
            try:
                append_analysis_summary(
                    working_dir=working_dir,
                    analysis_type="SASA",
                    statistics={
                        "n_frames": len(sasa_values),
                        "mean_sasa_nm2": mean_sasa,
                        "std_sasa_nm2": std_sasa,
                        "min_sasa_nm2": min_sasa,
                        "max_sasa_nm2": max_sasa,
                        "mean_sasa_angstrom2": mean_sasa * 100,  # Convert nm² to Ų
                        "min_sasa_angstrom2": min_sasa * 100,
                        "max_sasa_angstrom2": max_sasa * 100
                    },
                    files={
                        "topology": topology_file,
                        "trajectory": trajectory_file,
                        "output_csv": csv_filename
                    },
                    metadata={
                        "selection": selection,
                        "probe_radius_nm": probe_radius,
                        "probe_radius_angstrom": probe_radius * 10
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to write to summary file: {e}")
        
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except Exception as e:
                logger.debug(f"Failed to remove temp file {temp_file}: {e}")
        
        # Restore original directory
        if original_dir:
            os.chdir(original_dir)
        
        return {
            "success": True,
            "tool": "calculate_sasa",
            "mean_sasa": mean_sasa,
            "std_sasa": std_sasa,
            "min_sasa": min_sasa,
            "max_sasa": max_sasa,
            "num_frames": len(sasa_values),
            "sasa_values": sasa_values.tolist(),
            "times": times.tolist(),
            "frames": frames.tolist(),
            "output_csv": csv_filename,
            "units": "nm²",
            "message": f"Calculated SASA for {len(sasa_values)} frames. Mean: {mean_sasa:.2f} nm² | CSV: {csv_filename}"
        }
        
    except FileNotFoundError as e:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        if original_dir:
            os.chdir(original_dir)
        logger.error(f"File not found: {e}")
        return {
            "success": False,
            "error": str(e),
            "tool": "calculate_sasa"
        }
        
    except Exception as e:
        # Clean up temp files
        for temp_file in temp_files:
            try:
                if os.path.exists(temp_file):
                    os.remove(temp_file)
            except:
                pass
        if original_dir:
            os.chdir(original_dir)
        logger.error(f"SASA calculation failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "tool": "calculate_sasa"
        }


@tool
def plot_sasa(
    csv_file: str,
    output_figure: Optional[str] = None,
    time_col: str = "time",
    sasa_col: str = "sasa",
    title: str = "SASA vs Time",
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Plot SASA time-series from a CSV file (generated by calculate_sasa).
    
    Args:
        csv_file: CSV filename in working_dir (e.g., "sasa.csv")
        output_figure: Output figure filename only (default: "sasa_plot.png") - saved in working_dir
        time_col: Column name for time data (default: "time")
        sasa_col: Column name for SASA data (default: "sasa")
        title: Plot title (default: "SASA vs Time")
        working_dir: Working directory for analysis (where CSV is located)
        
    Returns:
        Dict with plot generation results
    """
    original_dir = None
    
    try:
        # Setup working directory
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)
        
        # Check dependencies
        try:
            import matplotlib
            matplotlib.use('Agg')  # Non-interactive backend
            import matplotlib.pyplot as plt
            import pandas as pd
        except ImportError as e:
            error_msg = f"Required plotting library not available: {e}"
            logger.error(error_msg)
            return {
                "success": False,
                "error": error_msg,
                "tool": "plot_sasa"
            }
        
        # CSV file should be in working_dir (just a filename)
        if not os.path.exists(csv_file):
            return {
                "success": False,
                "error": f"CSV file not found in working directory: {csv_file}",
                "tool": "plot_sasa"
            }
        
        # Read CSV
        df = pd.read_csv(csv_file)
        
        # Validate columns
        if time_col not in df.columns:
            return {
                "success": False,
                "error": f"Column '{time_col}' not found in CSV. Available: {list(df.columns)}",
                "tool": "plot_sasa"
            }
        if sasa_col not in df.columns:
            return {
                "success": False,
                "error": f"Column '{sasa_col}' not found in CSV. Available: {list(df.columns)}",
                "tool": "plot_sasa"
            }
        
        # Create plot
        plt.figure(figsize=(10, 6))
        plt.plot(df[time_col], df[sasa_col], linewidth=1.5, color='#2E86AB')
        plt.xlabel('Time (ps)', fontsize=12)
        plt.ylabel('SASA (nm²)', fontsize=12)
        plt.title(title, fontsize=14, fontweight='bold')
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        
        # Save figure (use filename only, already in working_dir)
        output_filename = output_figure if output_figure else "sasa_plot.png"
        plt.savefig(output_filename, dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"SASA plot saved to: {output_filename}")
        
        # Update analysis summary with plot file
        if working_dir:
            try:
                from .summary_logger import update_analysis_summary_with_files
                
                update_analysis_summary_with_files(
                    working_dir=working_dir,
                    analysis_type="SASA",
                    additional_files={"plot": output_filename}
                )
                logger.info(f"Updated SASA summary with plot: {output_filename}")
            except Exception as e:
                logger.warning(f"Could not update analysis summary with plot: {e}")
        
        # Restore original directory
        if original_dir:
            os.chdir(original_dir)
        
        return {
            "success": True,
            "tool": "plot_sasa",
            "output_figure": output_filename,
            "message": f"SASA plot saved to {output_filename}"
        }
        
    except Exception as e:
        if original_dir:
            os.chdir(original_dir)
        logger.error(f"SASA plotting failed: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "tool": "plot_sasa"
        }
