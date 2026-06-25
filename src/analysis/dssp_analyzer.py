"""
DSSP Analyzer - Secondary Structure Analysis Tool

Analyzes protein secondary structure using DSSP algorithm via MDAnalysis.
Calculates secondary structure percentages over time and generates heatmaps.
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
    from MDAnalysis.analysis import dssp as mda_dssp
    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    logger.warning("MDAnalysis not available - DSSP analysis will not work")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import matplotlib
    matplotlib.use('Agg')  # Use non-GUI backend
    import matplotlib.pyplot as plt
    import seaborn as sns
    HAS_PLOTTING = True
except ImportError:
    HAS_PLOTTING = False
    logger.warning("Matplotlib/Seaborn not available - plotting disabled")


# DSSP secondary structure code mapping
DSSP_CODE_MAP = {
    'H': 'α-helix',
    'B': 'β-bridge',
    'E': 'β-strand',
    'G': '3-helix',
    'I': 'π-helix',
    'T': 'Turn',
    'S': 'Bend',
    '-': 'Coil'
}


@tool
def analyze_secondary_structure(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein",
    output_prefix: Optional[str] = None,
    create_heatmap: bool = True,
    create_time_series: bool = True,
    save_raw_data: bool = True,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyze protein secondary structure using DSSP algorithm.
    
    This tool:
    - Calculates secondary structure for each residue at each frame
    - Computes percentage of each secondary structure type over time
    - Generates heatmap showing residue-by-residue secondary structure evolution
    - Creates time series plots of secondary structure percentages
    
    DSSP Secondary Structure Types:
    - H: α-helix (alpha helix)
    - B: β-bridge (isolated beta bridge)
    - E: β-strand (extended strand, participates in beta ladder)
    - G: 3-helix (3-10 helix)
    - I: π-helix (pi helix)
    - T: Turn (hydrogen bonded turn)
    - S: Bend (bend)
    - -: Coil (loops/random coil)
    
    Args:
        topology_file: Topology file (.gro, .pdb, .tpr) - full path
        trajectory_file: Trajectory file (.xtc, .trr, .dcd) - full path
        selection: Atom selection for DSSP analysis (default: "protein")
        output_prefix: Prefix for output files (default: "dssp")
        create_heatmap: Generate heatmap of secondary structure per residue (default: True)
        create_time_series: Generate time series plot of SS percentages (default: True)
        save_raw_data: Save raw DSSP data to file (default: True)
        working_dir: Working directory for analysis (optional)
        
    Returns:
        Dict with secondary structure analysis results including:
        - success: bool
        - n_frames: Number of analyzed frames
        - n_residues: Number of protein residues
        - ss_percentages: Average percentage of each SS type
        - ss_percentages_per_frame: SS percentages for each frame
        - output_files: Dictionary of output filenames (not full paths)
    """
    try:
        # Set default output prefix
        if output_prefix is None:
            output_prefix = "dssp"
        
        # Validate dependencies
        if not HAS_MDA:
            return {
                "success": False,
                "error": "MDAnalysis not available. Please install: pip install MDAnalysis"
            }
        
        if not HAS_NUMPY:
            return {
                "success": False,
                "error": "NumPy not available. Please install: pip install numpy"
            }
        
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

        # All outputs go under working_dir (matches analysis agent chdir behaviour)
        if working_dir:
            out_base = Path(working_dir)
            out_base.mkdir(parents=True, exist_ok=True)
        else:
            out_base = Path.cwd()
        
        logger.info(f"Running DSSP analysis on {trajectory_file} (output dir: {out_base})")
        
        # Load universe
        u = mda.Universe(topology_file, trajectory_file)
        
        # Select protein
        protein = u.select_atoms(selection)
        if len(protein) == 0:
            return {
                "success": False,
                "error": f"No atoms found with selection: '{selection}'"
            }
        
        # Filter to only residues with complete backbone atoms (N, CA, C, O)
        # DSSP requires equal numbers of these atoms - terminal residues or missing atoms will cause errors
        complete_resids = []
        for residue in protein.residues:
            backbone_atoms = residue.atoms.select_atoms("name N CA C O")
            # Check if residue has exactly 4 backbone atoms (one of each)
            atom_names = set(backbone_atoms.names)
            if atom_names == {'N', 'CA', 'C', 'O'}:
                complete_resids.append(residue.resid)
        
        if not complete_resids:
            return {
                "success": False,
                "error": f"No residues found with complete backbone atoms (N, CA, C, O). Original selection had {len(protein.residues)} residues."
            }
        
        # Select only residues with complete backbone
        resid_selection = " or ".join([f"resid {rid}" for rid in complete_resids])
        complete_protein = u.select_atoms(f"({selection}) and ({resid_selection})")
        
        logger.info(f"Filtered from {len(protein.residues)} to {len(complete_protein.residues)} residues with complete backbone")
        logger.info(f"Analyzing {len(complete_protein.residues)} residues across {len(u.trajectory)} frames")
        
        # Run DSSP analysis
        # DSSP expects an AtomGroup or Universe, not a 'select' keyword
        dssp = mda_dssp.DSSP(complete_protein)
        dssp.run()
        
        # Extract results
        # dssp.results.dssp is a 2D array: (n_frames, n_residues)
        dssp_array = dssp.results.dssp
        n_frames, n_residues = dssp_array.shape
        
        logger.info(f"DSSP analysis complete: {n_frames} frames, {n_residues} residues")
        
        # Calculate secondary structure percentages per frame
        ss_percentages_per_frame = {}
        for ss_code in DSSP_CODE_MAP.keys():
            ss_percentages_per_frame[ss_code] = []
        
        for frame_idx in range(n_frames):
            frame_data = dssp_array[frame_idx]
            total_residues = len(frame_data)
            
            for ss_code in DSSP_CODE_MAP.keys():
                count = np.sum(frame_data == ss_code)
                percentage = (count / total_residues) * 100.0
                ss_percentages_per_frame[ss_code].append(percentage)
        
        # Calculate average percentages across all frames
        ss_percentages = {}
        for ss_code, percentages in ss_percentages_per_frame.items():
            avg_percentage = np.mean(percentages)
            ss_percentages[ss_code] = float(avg_percentage)
        
        # Calculate time points (in ns)
        times = []
        for ts in u.trajectory:
            times.append(ts.time / 1000.0)  # Convert ps to ns
        
        # Prepare output files dictionary
        output_files = {}
        
        # Save raw DSSP data
        if save_raw_data:
            raw_data_file = str(out_base / f"{output_prefix}_raw_data.dat")
            with open(raw_data_file, 'w') as f:
                f.write("# DSSP Secondary Structure Assignment\n")
                f.write(f"# Topology: {topology_file}\n")
                f.write(f"# Trajectory: {trajectory_file}\n")
                f.write(f"# Frames: {n_frames}, Residues: {n_residues}\n")
                f.write("# DSSP Codes: H=α-helix, B=β-bridge, E=β-strand, G=3-helix, I=π-helix, T=Turn, S=Bend, -=Coil\n")
                f.write("#\n")
                f.write("# Frame\tResidue\tDSSP_Code\n")
                
                for frame_idx in range(n_frames):
                    for res_idx in range(n_residues):
                        ss_code = dssp_array[frame_idx, res_idx]
                        f.write(f"{frame_idx}\t{res_idx}\t{ss_code}\n")
            
            output_files['raw_data'] = raw_data_file
            logger.info(f"Raw DSSP data saved to {raw_data_file}")
        
        # Save percentage data
        percentage_file = str(out_base / f"{output_prefix}_percentages.dat")
        with open(percentage_file, 'w') as f:
            f.write("# Secondary Structure Percentages Over Time\n")
            # Build header
            ss_types = '\t'.join([f'{DSSP_CODE_MAP[code]}({code})' for code in DSSP_CODE_MAP.keys()])
            f.write(f"# Time(ns)\t{ss_types}\n")
            
            for frame_idx in range(n_frames):
                time_ns = times[frame_idx]
                percentages = [ss_percentages_per_frame[code][frame_idx] for code in DSSP_CODE_MAP.keys()]
                percentage_str = '\t'.join([f'{p:.2f}' for p in percentages])
                f.write(f"{time_ns:.4f}\t{percentage_str}\n")
        
        output_files['percentages'] = percentage_file
        logger.info(f"Percentage data saved to {percentage_file}")
        
        # Create heatmap
        if create_heatmap and HAS_PLOTTING:
            heatmap_file = str(out_base / f"{output_prefix}_heatmap.png")
            
            # Convert DSSP codes to numeric values for heatmap
            # H=1, B=2, E=3, G=4, I=5, T=6, S=7, -=8
            code_to_num = {'H': 1, 'B': 2, 'E': 3, 'G': 4, 'I': 5, 'T': 6, 'S': 7, '-': 8}
            numeric_array = np.vectorize(code_to_num.get)(dssp_array)
            
            # Create figure
            fig, ax = plt.subplots(figsize=(12, 8))
            
            # Create heatmap
            cmap = plt.cm.get_cmap('tab10', 8)
            im = ax.imshow(numeric_array.T, aspect='auto', cmap=cmap, 
                          interpolation='nearest', vmin=1, vmax=8)
            
            # Set labels
            ax.set_xlabel('Frame', fontsize=12)
            ax.set_ylabel('Residue', fontsize=12)
            ax.set_title('Secondary Structure Evolution', fontsize=14, fontweight='bold')
            
            # Create colorbar with labels
            cbar = plt.colorbar(im, ax=ax, ticks=np.arange(1, 9))
            cbar.ax.set_yticklabels([DSSP_CODE_MAP[code] for code in ['H', 'B', 'E', 'G', 'I', 'T', 'S', '-']])
            cbar.set_label('Secondary Structure Type', fontsize=12)
            
            # Set tick intervals for better readability
            if n_frames > 50:
                ax.set_xticks(np.linspace(0, n_frames-1, 10))
            if n_residues > 50:
                ax.set_yticks(np.linspace(0, n_residues-1, 10))
            
            plt.tight_layout()
            plt.savefig(heatmap_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            output_files['heatmap'] = heatmap_file
            logger.info(f"Heatmap saved to {heatmap_file}")
        
        # Create time series plot
        if create_time_series and HAS_PLOTTING:
            timeseries_file = str(out_base / f"{output_prefix}_timeseries.png")
            
            fig, ax = plt.subplots(figsize=(12, 6))
            
            # Plot major secondary structure types
            colors = {'H': '#e74c3c', 'E': '#3498db', 'T': '#f39c12', 'G': '#9b59b6', '-': '#95a5a6'}
            major_codes = ['H', 'E', 'T', 'G', '-']
            
            for code in major_codes:
                if code in ss_percentages_per_frame:
                    percentages = ss_percentages_per_frame[code]
                    color = colors.get(code, '#000000')
                    label = f"{DSSP_CODE_MAP[code]} ({code})"
                    ax.plot(times, percentages, label=label, color=color, linewidth=2, alpha=0.8)
            
            ax.set_xlabel('Time (ns)', fontsize=12)
            ax.set_ylabel('Percentage (%)', fontsize=12)
            ax.set_title('Secondary Structure Content Over Time', fontsize=14, fontweight='bold')
            ax.legend(loc='best', fontsize=10)
            ax.grid(True, alpha=0.3)
            ax.set_ylim(0, 100)
            
            plt.tight_layout()
            plt.savefig(timeseries_file, dpi=300, bbox_inches='tight')
            plt.close()
            
            output_files['timeseries'] = timeseries_file
            logger.info(f"Time series plot saved to {timeseries_file}")
        
        # Calculate stability metrics
        # Measure variability in secondary structure
        ss_stability = {}
        for code in DSSP_CODE_MAP.keys():
            percentages = ss_percentages_per_frame[code]
            std_dev = np.std(percentages)
            ss_stability[code] = float(std_dev)
        
        # Prepare summary report
        summary_text = f"""
DSSP Secondary Structure Analysis Summary
==========================================

Trajectory Information:
  - Topology: {topology_file}
  - Trajectory: {trajectory_file}
  - Selection: {selection}
  - Frames analyzed: {n_frames}
  - Residues analyzed: {n_residues}

Average Secondary Structure Content:
"""
        for code in ['H', 'E', 'G', 'I', 'T', 'S', 'B', '-']:
            ss_name = DSSP_CODE_MAP[code]
            avg_pct = ss_percentages[code]
            std_pct = ss_stability[code]
            summary_text += f"  - {ss_name:12s} ({code}): {avg_pct:6.2f}% ± {std_pct:5.2f}%\n"
        
        summary_text += f"\nOutput Files:\n"
        for file_type, file_path in output_files.items():
            summary_text += f"  - {file_type:15s}: {file_path}\n"
        
        # Save summary
        summary_file = str(out_base / f"{output_prefix}_summary.txt")
        with open(summary_file, 'w') as f:
            f.write(summary_text)
        output_files['summary'] = summary_file
        logger.info(f"Summary saved to {summary_file}")
        
        # Print summary to log
        logger.info("\n" + summary_text)
        
        # Calculate per-residue secondary structure stability for important regions
        per_residue_stability = []
        for res_idx in range(n_residues):
            # Get all assignments for this residue across frames
            residue_assignments = dssp_array[:, res_idx]
            # Count how many different SS types this residue adopts
            unique_types = len(np.unique(residue_assignments))
            # Calculate most common SS type
            unique, counts = np.unique(residue_assignments, return_counts=True)
            most_common_ss = unique[np.argmax(counts)]
            persistence = (np.max(counts) / n_frames) * 100  # % time in most common state
            
            per_residue_stability.append({
                'residue_id': int(res_idx + 1),  # 1-indexed
                'most_common_ss': most_common_ss,
                'persistence_percent': float(persistence),
                'n_transitions': int(unique_types - 1)
            })
        
        # Find most stable helix regions (residues persistent in H state)
        stable_helices = [r for r in per_residue_stability 
                         if r['most_common_ss'] == 'H' and r['persistence_percent'] > 80]
        stable_helices_sorted = sorted(stable_helices, key=lambda x: x['persistence_percent'], reverse=True)[:5]
        
        # Find most stable sheet regions (residues persistent in E state)
        stable_sheets = [r for r in per_residue_stability 
                        if r['most_common_ss'] == 'E' and r['persistence_percent'] > 80]
        stable_sheets_sorted = sorted(stable_sheets, key=lambda x: x['persistence_percent'], reverse=True)[:5]
        
        # Find most flexible regions (residues with many transitions)
        flexible_regions = sorted(per_residue_stability, 
                                 key=lambda x: (x['n_transitions'], -x['persistence_percent']), 
                                 reverse=True)[:5]
        
        # Write to analysis summary file
        if working_dir:
            try:
                append_analysis_summary(
                    working_dir=str(out_base),
                    analysis_type="DSSP_SecondaryStructure",
                    statistics={
                        "n_frames": int(n_frames),
                        "n_residues": int(n_residues),
                        "avg_helix_percent": float(ss_percentages['H']),
                        "avg_sheet_percent": float(ss_percentages['E']),
                        "avg_turn_percent": float(ss_percentages['T']),
                        "avg_coil_percent": float(ss_percentages['-']),
                        "helix_stability_std": float(ss_stability['H']),
                        "sheet_stability_std": float(ss_stability['E'])
                    },
                    files={
                        "topology": topology_file,
                        "trajectory": trajectory_file,
                        **output_files
                    },
                    metadata={
                        "selection": selection,
                        "dssp_codes_used": list(DSSP_CODE_MAP.keys()),
                        "most_stable_helix_residues": stable_helices_sorted,
                        "most_stable_sheet_residues": stable_sheets_sorted,
                        "most_flexible_residues": flexible_regions
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to write to summary file: {e}")
        
        # Prepare results (output_files contains just filenames)
        results = {
            "success": True,
            "n_frames": int(n_frames),
            "n_residues": int(n_residues),
            "ss_percentages": ss_percentages,
            "ss_stability": ss_stability,
            "ss_percentages_per_frame": {k: [float(v) for v in vals] 
                                         for k, vals in ss_percentages_per_frame.items()},
            "output_files": output_files,
            "summary": summary_text
        }
        
        return results
        
    except Exception as e:
        logger.error(f"DSSP analysis failed: {str(e)}", exc_info=True)
        return {
            "success": False,
            "error": str(e)
        }
