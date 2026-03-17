"""
MD Data Plotter - Visualization tool for MD analysis data

Creates publication-quality plots for RMSD, RMSF, Rg, Energy, and other MD metrics.
Supports single-panel and multi-panel (subplot) layouts.
"""
import os
import logging
from typing import Dict, Any, Optional, List, Tuple
from pathlib import Path
from langchain.tools import tool

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend for server environments
    import matplotlib.pyplot as plt
    import matplotlib.gridspec as gridspec
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib not available - plotting will be disabled")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def parse_data_file(file_path: str) -> Tuple[List[List[float]], List[str]]:
    """
    Parse data file (.xvg, .dat, .csv) and extract columns.
    
    Args:
        file_path: Path to data file
        
    Returns:
        Tuple of (data_columns, column_names)
    """
    data_columns = []
    column_names = []
    
    with open(file_path, 'r') as f:
        for line in f:
            line = line.strip()
            
            # Skip empty lines
            if not line:
                continue
            
            # Parse headers (XVG format)
            if line.startswith('@'):
                if 'xaxis label' in line.lower():
                    # Extract x-axis label
                    label = line.split('"')[1] if '"' in line else "X"
                    if not column_names:
                        column_names.append(label)
                elif 'yaxis label' in line.lower():
                    # Extract y-axis label
                    label = line.split('"')[1] if '"' in line else "Y"
                    if len(column_names) == 1:
                        column_names.append(label)
                continue
            
            # Skip comment lines
            if line.startswith('#'):
                # Try to extract column names from header
                if 'Frame' in line or 'Time' in line or 'Residue' in line:
                    parts = line[1:].strip().split('\t')
                    column_names = [p.strip() for p in parts]
                continue
            
            # Parse data
            try:
                parts = line.split()
                values = [float(p) for p in parts]
                
                # Initialize columns on first data row
                if not data_columns:
                    data_columns = [[] for _ in values]
                
                # Append values to respective columns
                for i, val in enumerate(values):
                    if i < len(data_columns):
                        data_columns[i].append(val)
                        
            except ValueError:
                continue
    
    # Set default column names if not found
    if not column_names:
        column_names = [f"Column {i+1}" for i in range(len(data_columns))]
    elif len(column_names) < len(data_columns):
        # Add missing column names
        for i in range(len(column_names), len(data_columns)):
            column_names.append(f"Column {i+1}")
    
    return data_columns, column_names


@tool
def plot_md_data(
    data_files: List[str],
    output_file: str,
    plot_type: str = "line",
    titles: Optional[List[str]] = None,
    xlabel: Optional[str] = None,
    ylabel: Optional[str] = None,
    labels: Optional[List[str]] = None,
    colors: Optional[List[str]] = None,
    figsize: Tuple[int, int] = (10, 6),
    dpi: int = 300,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Plot MD analysis data from one or more data files (single panel).
    
    Creates a single-panel plot for visualizing RMSD, RMSF, Rg, or energy data.
    Supports overlay of multiple datasets on the same axes.
    
    Args:
        data_files: List of data file paths to plot (.xvg, .dat, .csv)
        output_file: Output image filename only (e.g., "plot.png") - saved in working_dir
        plot_type: Type of plot ("line", "scatter", "bar") - default: "line"
        titles: Plot title (optional)
        xlabel: X-axis label (optional, auto-detected from file if available)
        ylabel: Y-axis label (optional, auto-detected from file if available)
        labels: Legend labels for each data file (optional)
        colors: Line/marker colors for each dataset (optional)
        figsize: Figure size as (width, height) in inches - default: (10, 6)
        dpi: Resolution in dots per inch - default: 300
        working_dir: Working directory for analysis (files will be written here)
        
    Returns:
        Dict with plotting results
    """
    try:
        if not HAS_MATPLOTLIB:
            return {
                "success": False,
                "error": "matplotlib not available - cannot create plots"
            }
        
        # Convert file paths to absolute before changing directory
        abs_data_files = []
        original_dir = os.getcwd()
        
        for data_file in data_files:
            if os.path.isabs(data_file):
                abs_data_files.append(data_file)
            else:
                # If working_dir is specified, resolve relative paths from there
                if working_dir:
                    abs_data_files.append(os.path.join(working_dir, data_file))
                else:
                    abs_data_files.append(os.path.abspath(data_file))
        
        # Validate that all files exist
        for abs_path, rel_path in zip(abs_data_files, data_files):
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": f"Data file not found: {rel_path}"
                }
        
        # Setup working directory for output
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            os.chdir(working_dir)
        
        # Create figure
        fig, ax = plt.subplots(figsize=figsize, dpi=dpi)
        
        # Default colors if not provided
        if colors is None:
            colors = [f"C{i}" for i in range(len(data_files))]
        
        # Plot each data file (use absolute paths)
        for idx, (abs_file, rel_file) in enumerate(zip(abs_data_files, data_files)):
            # Parse data
            data_columns, column_names = parse_data_file(abs_file)
            
            if len(data_columns) < 2:
                logger.warning(f"Insufficient data columns in {rel_file}, skipping")
                continue
            
            x_data = data_columns[0]
            y_data = data_columns[1]
            
            # Determine label
            if labels is not None and idx < len(labels):
                label = labels[idx]
            else:
                label = Path(rel_file).stem
            
            # Determine color
            color = colors[idx] if idx < len(colors) else None
            
            # Plot based on type
            if plot_type == "line":
                ax.plot(x_data, y_data, label=label, color=color, linewidth=2)
            elif plot_type == "scatter":
                ax.scatter(x_data, y_data, label=label, color=color, alpha=0.6)
            elif plot_type == "bar":
                ax.bar(x_data, y_data, label=label, color=color, alpha=0.7)
            
            # Auto-detect axis labels from first file
            if idx == 0 and not xlabel and len(column_names) > 0:
                xlabel = column_names[0]
            if idx == 0 and not ylabel and len(column_names) > 1:
                ylabel = column_names[1]
        
        # Set labels
        if xlabel:
            ax.set_xlabel(xlabel, fontsize=12, fontweight='bold')
        if ylabel:
            ax.set_ylabel(ylabel, fontsize=12, fontweight='bold')
        
        # Set title
        if titles is not None and len(titles) > 0:
            ax.set_title(titles[0], fontsize=14, fontweight='bold')
        
        # Add legend if multiple datasets
        if len(data_files) > 1:
            ax.legend(frameon=True, shadow=True, fontsize=10)
        
        # Grid
        ax.grid(True, alpha=0.3, linestyle='--')
        
        # Tight layout
        plt.tight_layout()
        
        # Save figure (use filename only, already in working_dir)
        plt.savefig(output_file, dpi=dpi, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Plot saved to {output_file}")
        
        if working_dir:
            os.chdir(original_dir)
        
        return {
            "success": True,
            "output_file": output_file,
            "n_datasets": len(data_files),
            "plot_type": plot_type,
            "message": f"Successfully created {plot_type} plot with {len(data_files)} dataset(s)"
        }
        
    except Exception as e:
        logger.exception(f"Plotting failed: {e}")
        if working_dir and 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"Plotting failed: {str(e)}"
        }


@tool
def plot_md_multipanel(
    data_files: List[str],
    output_file: str,
    layout: str = "vertical",
    titles: Optional[List[str]] = None,
    xlabels: Optional[List[str]] = None,
    ylabels: Optional[List[str]] = None,
    plot_types: Optional[List[str]] = None,
    colors: Optional[List[str]] = None,
    figsize: Optional[Tuple[int, int]] = None,
    dpi: int = 300,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create multi-panel plots for comparing multiple MD analyses.
    
    Creates a figure with multiple subplots, one for each data file.
    Useful for comparing RMSD, RMSF, Rg, and energy in a single figure.
    
    Args:
        data_files: List of data file paths, one per panel (.xvg, .dat, .csv)
        output_file: Output image file path (.png, .pdf, .svg)
        layout: Subplot layout ("vertical", "horizontal", "grid") - default: "vertical"
        titles: List of subplot titles (optional)
        xlabels: List of x-axis labels for each subplot (optional)
        ylabels: List of y-axis labels for each subplot (optional)
        plot_types: List of plot types for each panel (optional, default: "line")
        colors: List of colors for each panel (optional)
        figsize: Figure size as (width, height) in inches (auto-sized if None)
        dpi: Resolution in dots per inch - default: 300
        working_dir: Working directory for analysis
        
    Returns:
        Dict with plotting results
    """
    try:
        if not HAS_MATPLOTLIB:
            return {
                "success": False,
                "error": "matplotlib not available - cannot create plots"
            }
        
        # Convert file paths to absolute before changing directory
        # This handles cases where paths include working_dir prefix
        abs_data_files = []
        original_dir = os.getcwd()
        
        for data_file in data_files:
            # If path is already absolute, use it
            if os.path.isabs(data_file):
                abs_data_files.append(data_file)
            else:
                # If working_dir is specified, resolve relative paths from there
                if working_dir:
                    abs_data_files.append(os.path.join(working_dir, data_file))
                else:
                    # Make it absolute relative to current directory
                    abs_data_files.append(os.path.abspath(data_file))
        
        # Validate that all files exist (before any chdir)
        for abs_path, rel_path in zip(abs_data_files, data_files):
            if not os.path.exists(abs_path):
                return {
                    "success": False,
                    "error": f"Data file not found: {rel_path}"
                }
        
        # Setup working directory for output
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            os.chdir(working_dir)
        
        n_panels = len(data_files)
        
        # Determine subplot layout
        if layout == "vertical":
            nrows, ncols = n_panels, 1
            if not figsize:
                figsize = (10, 4 * n_panels)
        elif layout == "horizontal":
            nrows, ncols = 1, n_panels
            if not figsize:
                figsize = (6 * n_panels, 5)
        elif layout == "grid":
            ncols = int(np.ceil(np.sqrt(n_panels)))
            nrows = int(np.ceil(n_panels / ncols))
            if not figsize:
                figsize = (6 * ncols, 4 * nrows)
        else:
            if working_dir:
                os.chdir(original_dir)
            return {
                "success": False,
                "error": f"Invalid layout: {layout}. Use 'vertical', 'horizontal', or 'grid'"
            }
        
        # Create figure with subplots
        fig, axes = plt.subplots(nrows, ncols, figsize=figsize, dpi=dpi)
        
        # Ensure axes is iterable
        if n_panels == 1:
            axes = [axes]
        else:
            axes = axes.flatten()
        
        # Default plot types
        if plot_types is None:
            plot_types = ["line"] * n_panels
        
        # Default colors
        if colors is None:
            colors = [f"C{i}" for i in range(n_panels)]
        
        # Plot each panel (use absolute paths for reading)
        for idx, (abs_file, rel_file, ax) in enumerate(zip(abs_data_files, data_files, axes)):
            # Parse data
            data_columns, column_names = parse_data_file(abs_file)
            
            if len(data_columns) < 2:
                logger.warning(f"Insufficient data columns in {rel_file}, skipping panel {idx+1}")
                ax.text(0.5, 0.5, f"No data\n{Path(rel_file).name}", 
                       ha='center', va='center', transform=ax.transAxes)
                continue
            
            x_data = data_columns[0]
            y_data = data_columns[1]
            
            # Determine plot type
            plot_type = plot_types[idx] if idx < len(plot_types) else "line"
            
            # Determine color
            color = colors[idx] if idx < len(colors) else None
            
            # Plot based on type
            if plot_type == "line":
                ax.plot(x_data, y_data, color=color, linewidth=2)
            elif plot_type == "scatter":
                ax.scatter(x_data, y_data, color=color, alpha=0.6)
            elif plot_type == "bar":
                ax.bar(x_data, y_data, color=color, alpha=0.7)
            
            # Set labels
            if xlabels is not None and idx < len(xlabels):
                ax.set_xlabel(xlabels[idx], fontsize=11, fontweight='bold')
            elif len(column_names) > 0:
                ax.set_xlabel(column_names[0], fontsize=11, fontweight='bold')
            
            if ylabels is not None and idx < len(ylabels):
                ax.set_ylabel(ylabels[idx], fontsize=11, fontweight='bold')
            elif len(column_names) > 1:
                ax.set_ylabel(column_names[1], fontsize=11, fontweight='bold')
            
            # Set title
            if titles is not None and idx < len(titles):
                ax.set_title(titles[idx], fontsize=12, fontweight='bold')
            else:
                ax.set_title(Path(data_file).stem.replace('_', ' ').title(), 
                           fontsize=12, fontweight='bold')
            
            # Grid
            ax.grid(True, alpha=0.3, linestyle='--')
        
        # Hide extra subplots if grid layout
        for idx in range(n_panels, len(axes)):
            axes[idx].set_visible(False)
        
        # Adjust spacing
        plt.tight_layout()
        
        # Save figure (use filename only, already in working_dir)
        plt.savefig(output_file, dpi=dpi, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Multi-panel plot saved to {output_file}")
        
        if working_dir:
            os.chdir(original_dir)
        
        return {
            "success": True,
            "output_file": output_file,
            "n_panels": n_panels,
            "layout": layout,
            "message": f"Successfully created {n_panels}-panel {layout} plot"
        }
        
    except Exception as e:
        logger.exception(f"Multi-panel plotting failed: {e}")
        if working_dir and 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"Multi-panel plotting failed: {str(e)}"
        }


@tool
def plot_combined_data(
    data_files: List[str],
    output_file: str,
    data_columns: Optional[List[int]] = None,
    subplot_arrangement: Optional[Tuple[int, int]] = None,
    shared_xaxis: bool = True,
    titles: Optional[List[str]] = None,
    xlabel: Optional[str] = None,
    ylabels: Optional[List[str]] = None,
    colors: Optional[List[str]] = None,
    figsize: Tuple[int, int] = (12, 8),
    dpi: int = 300,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create combined plots from a single data file with multiple columns.
    
    Useful for plotting multiple energy terms, multiple properties, or
    comparing different metrics from the same simulation.
    
    Args:
        data_files: List containing one data file with multiple columns
        output_file: Output image file path (.png, .pdf, .svg)
        data_columns: List of column indices to plot (e.g., [1, 2, 3] for columns after x-axis)
        subplot_arrangement: (rows, cols) for subplot grid (auto if None)
        shared_xaxis: Whether to share x-axis across subplots - default: True
        titles: List of subplot titles (optional)
        xlabel: Common x-axis label (optional)
        ylabels: List of y-axis labels for each subplot (optional)
        colors: List of colors for each subplot (optional)
        figsize: Figure size as (width, height) in inches - default: (12, 8)
        dpi: Resolution in dots per inch - default: 300
        working_dir: Working directory for analysis
        
    Returns:
        Dict with plotting results
    """
    try:
        if not HAS_MATPLOTLIB:
            return {
                "success": False,
                "error": "matplotlib not available - cannot create plots"
            }
        
        # Convert file path to absolute before changing directory
        original_dir = os.getcwd()
        
        # Validate input file
        if not data_files or len(data_files) == 0:
            return {
                "success": False,
                "error": "No data files provided"
            }
        
        data_file = data_files[0]
        if os.path.isabs(data_file):
            abs_data_file = data_file
        else:
            # If working_dir is specified, resolve relative paths from there
            if working_dir:
                abs_data_file = os.path.join(working_dir, data_file)
            else:
                abs_data_file = os.path.abspath(data_file)
        
        if not os.path.exists(abs_data_file):
            return {
                "success": False,
                "error": f"Data file not found: {data_file}"
            }
        
        # Setup working directory for output
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            os.chdir(working_dir)
        
        # Parse data file (use absolute path)
        data_columns_all, column_names = parse_data_file(abs_data_file)
        
        if len(data_columns_all) < 2:
            if working_dir:
                os.chdir(original_dir)
            return {
                "success": False,
                "error": "Insufficient data columns in file"
            }
        
        # Determine which columns to plot
        x_data = data_columns_all[0]
        
        if data_columns:
            y_data_list = [data_columns_all[i] for i in data_columns if i < len(data_columns_all)]
        else:
            # Plot all columns except the first (x-axis)
            y_data_list = data_columns_all[1:]
        
        n_plots = len(y_data_list)
        
        # Determine subplot arrangement
        if subplot_arrangement:
            nrows, ncols = subplot_arrangement
        else:
            ncols = 2 if n_plots > 2 else 1
            nrows = int(np.ceil(n_plots / ncols))
        
        # Create subplots
        fig, axes = plt.subplots(nrows, ncols, figsize=figsize, dpi=dpi, 
                                sharex=shared_xaxis)
        
        # Ensure axes is iterable
        if n_plots == 1:
            axes = [axes]
        else:
            axes = axes.flatten()
        
        # Default colors
        if colors is None:
            colors = [f"C{i}" for i in range(n_plots)]
        
        # Plot each y-column
        for idx, (y_data, ax) in enumerate(zip(y_data_list, axes)):
            color = colors[idx] if idx < len(colors) else None
            
            ax.plot(x_data, y_data, color=color, linewidth=2)
            
            # Set ylabel
            if ylabels is not None and idx < len(ylabels):
                ax.set_ylabel(ylabels[idx], fontsize=11, fontweight='bold')
            elif idx + 1 < len(column_names):
                ax.set_ylabel(column_names[idx + 1], fontsize=11, fontweight='bold')
            
            # Set title
            if titles is not None and idx < len(titles):
                ax.set_title(titles[idx], fontsize=12, fontweight='bold')
            
            # Grid
            ax.grid(True, alpha=0.3, linestyle='--')
            
            # Set xlabel for bottom row or if not sharing x-axis
            if not shared_xaxis or idx >= (nrows - 1) * ncols:
                if xlabel:
                    ax.set_xlabel(xlabel, fontsize=11, fontweight='bold')
                elif len(column_names) > 0:
                    ax.set_xlabel(column_names[0], fontsize=11, fontweight='bold')
        
        # Hide extra subplots
        for idx in range(n_plots, len(axes)):
            axes[idx].set_visible(False)
        
        # Add common xlabel if shared x-axis
        if shared_xaxis and xlabel:
            fig.text(0.5, 0.02, xlabel, ha='center', fontsize=12, fontweight='bold')
        
        # Adjust spacing
        plt.tight_layout()
        
        # Save figure (use filename only, already in working_dir)
        plt.savefig(output_file, dpi=dpi, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Combined plot saved to {output_file}")
        
        if working_dir:
            os.chdir(original_dir)
        
        return {
            "success": True,
            "output_file": output_file,
            "n_plots": n_plots,
            "message": f"Successfully created combined plot with {n_plots} subplots"
        }
        
    except Exception as e:
        logger.exception(f"Combined plotting failed: {e}")
        if working_dir and 'original_dir' in locals():
            os.chdir(original_dir)
        return {
            "success": False,
            "error": f"Combined plotting failed: {str(e)}"
        }
