"""
Energy Analysis Tool - Extract and analyze energy terms from MD simulations

Analyzes potential energy, kinetic energy, temperature, pressure, etc.
"""
import os
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from langchain.tools import tool

logger = logging.getLogger(__name__)

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


@tool
def analyze_energy(
    energy_file: str,
    terms: Optional[List[str]] = None,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze energy terms from GROMACS energy file (.edr).
    
    Extracts and analyzes energy components like potential, kinetic energy,
    temperature, pressure, and other thermodynamic properties.
    
    Args:
        energy_file: GROMACS energy file (.edr)
        terms: List of energy terms to extract (default: ["Potential", "Kinetic-En.", "Temperature"])
        output_file: Output file path for energy data (.xvg)
        working_dir: Working directory for analysis
        
    Returns:
        Dict with energy analysis results
    """
    try:
        # Setup working directory
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)
        
        # Validate input file
        if not os.path.exists(energy_file):
            return {
                "success": False,
                "error": f"Energy file not found: {energy_file}"
            }
        
        # Default energy terms
        if terms is None:
            terms = ["Potential", "Kinetic-En.", "Temperature"]
        
        # Determine output file
        if not output_file:
            output_file = "energy.xvg"
        
        import subprocess
        
        # Use gmx energy to extract terms
        logger.info(f"Extracting energy terms: {', '.join(terms)}")
        
        cmd = [
            "gmx", "energy",
            "-f", energy_file,
            "-o", output_file
        ]
        
        # Create input for term selection
        # First, get list of available terms
        list_cmd = ["gmx", "energy", "-f", energy_file]
        list_result = subprocess.run(
            list_cmd,
            input="0\n",  # Exit without selection
            capture_output=True,
            text=True
        )
        
        # Parse available terms from output
        available_terms = {}
        for line in list_result.stdout.split('\n'):
            # Look for lines like "  1  Bond             2  Angle            3  Proper-Dih."
            parts = line.split()
            i = 0
            while i < len(parts) - 1:
                if parts[i].isdigit():
                    term_idx = int(parts[i])
                    term_name = parts[i + 1]
                    available_terms[term_name] = term_idx
                    i += 2
                else:
                    i += 1
        
        # Map requested terms to indices
        term_indices = []
        found_terms = []
        for term in terms:
            for avail_term, idx in available_terms.items():
                if term.lower() in avail_term.lower():
                    term_indices.append(idx)
                    found_terms.append(avail_term)
                    break
        
        if not term_indices:
            # Try common defaults
            term_indices = [10, 11, 14]  # Typical indices for Potential, Kinetic, Temp
            found_terms = ["Potential", "Kinetic-En.", "Temperature"]
        
        # Run gmx energy with selected terms
        selection_input = '\n'.join(map(str, term_indices)) + '\n0\n'
        
        result = subprocess.run(
            cmd,
            input=selection_input,
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            if working_dir:
                os.chdir(original_dir)
            return {
                "success": False,
                "error": f"gmx energy failed: {result.stderr}"
            }
        
        # Parse output file
        energy_data = {term: [] for term in found_terms}
        times = []
        
        if os.path.exists(output_file):
            with open(output_file, 'r') as f:
                for line in f:
                    if line.startswith('#') or line.startswith('@'):
                        continue
                    parts = line.split()
                    if len(parts) >= len(found_terms) + 1:
                        times.append(float(parts[0]))
                        for i, term in enumerate(found_terms):
                            energy_data[term].append(float(parts[i + 1]))
        
        # Calculate statistics for each term
        results = {
            "success": True,
            "n_frames": len(times),
            "output_file": output_file,
            "terms": {}
        }
        
        for term, values in energy_data.items():
            if values:
                if HAS_NUMPY:
                    mean_val = float(np.mean(values))
                    std_val = float(np.std(values))
                    min_val = float(np.min(values))
                    max_val = float(np.max(values))
                else:
                    mean_val = sum(values) / len(values)
                    std_val = (sum((x - mean_val)**2 for x in values) / len(values)) ** 0.5
                    min_val = min(values)
                    max_val = max(values)
                
                results["terms"][term] = {
                    "mean": mean_val,
                    "std": std_val,
                    "min": min_val,
                    "max": max_val
                }
        
        # Create summary message
        summary_parts = []
        for term, stats in results["terms"].items():
            summary_parts.append(f"{term}: {stats['mean']:.2f} ± {stats['std']:.2f}")
        
        results["message"] = f"Energy analysis complete. {', '.join(summary_parts)}"
        
        if working_dir:
            os.chdir(original_dir)
        
        return results
        
    except Exception as e:
        logger.exception(f"Energy analysis failed: {e}")
        if working_dir and 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"Energy analysis failed: {str(e)}"
        }


@tool
def extract_trajectory_metrics(
    trajectory_file: str,
    topology_file: str,
    output_dir: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Extract basic metrics from trajectory file.
    
    Gets trajectory information like number of frames, time range, and file size.
    
    Args:
        trajectory_file: Trajectory file (.xtc, .trr)
        topology_file: Topology file (.gro, .pdb, .tpr)
        output_dir: Output directory for extracted data
        working_dir: Working directory for analysis
        
    Returns:
        Dict with trajectory metrics
    """
    try:
        # Setup working directory
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)
        
        # Validate input files
        if not os.path.exists(trajectory_file):
            return {
                "success": False,
                "error": f"Trajectory file not found: {trajectory_file}"
            }
        
        if not os.path.exists(topology_file):
            return {
                "success": False,
                "error": f"Topology file not found: {topology_file}"
            }
        
        import subprocess
        
        # Use gmx check to get trajectory info
        cmd = ["gmx", "check", "-f", trajectory_file]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True
        )
        
        # Parse output for metrics
        n_frames = 0
        time_range = (0.0, 0.0)
        
        for line in result.stdout.split('\n'):
            if 'Reading frame' in line and 'time' in line:
                # Extract time from last frame
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == 'time' and i + 1 < len(parts):
                        time_val = float(parts[i + 1])
                        time_range = (time_range[0], time_val)
            elif 'frames' in line.lower():
                parts = line.split()
                for part in parts:
                    if part.isdigit():
                        n_frames = int(part)
                        break
        
        # Get file size
        file_size_mb = os.path.getsize(trajectory_file) / (1024 * 1024)
        
        if working_dir:
            os.chdir(original_dir)
        
        return {
            "success": True,
            "n_frames": n_frames,
            "time_range": time_range,
            "file_size_mb": file_size_mb,
            "trajectory_file": trajectory_file,
            "message": f"Trajectory has {n_frames} frames spanning {time_range[0]:.1f}-{time_range[1]:.1f} ps"
        }
        
    except Exception as e:
        logger.exception(f"Trajectory metrics extraction failed: {e}")
        if working_dir and 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"Trajectory metrics extraction failed: {str(e)}"
        }
