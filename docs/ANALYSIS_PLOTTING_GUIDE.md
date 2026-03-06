# Analysis Agent Plotting Tools

## Overview

The Analysis Agent now includes three powerful plotting tools for visualizing MD simulation data. These tools can create publication-quality plots from RMSD, RMSF, Radius of Gyration, Energy, and other analysis outputs.

## Available Plotting Tools

### 1. `plot_md_data` - Single Panel Plots

Create single-panel plots with support for overlaying multiple datasets.

**Use Cases:**
- Plot RMSD over time
- Compare RMSD from multiple simulations
- Visualize RMSF per-residue data
- Plot energy terms vs time

**Parameters:**
```python
plot_md_data(
    data_files: List[str],        # List of data files to plot
    output_file: str,              # Output image path (.png, .pdf, .svg)
    plot_type: str = "line",       # "line", "scatter", or "bar"
    titles: Optional[List[str]] = None,  # Plot title
    xlabel: Optional[str] = None,  # X-axis label (auto-detected)
    ylabel: Optional[str] = None,  # Y-axis label (auto-detected)
    labels: Optional[List[str]] = None,  # Legend labels
    colors: Optional[List[str]] = None,  # Colors for each dataset
    figsize: Tuple[int, int] = (10, 6),  # Figure size in inches
    dpi: int = 300,                # Resolution
    working_dir: Optional[str] = None
)
```

**Example:**
```python
# Plot RMSD from a single simulation
plot_md_data(
    data_files=["rmsd.dat"],
    output_file="rmsd_plot.png",
    xlabel="Time (ps)",
    ylabel="RMSD (Å)",
    titles=["RMSD Analysis"]
)

# Compare multiple simulations
plot_md_data(
    data_files=["sim1_rmsd.dat", "sim2_rmsd.dat", "sim3_rmsd.dat"],
    output_file="rmsd_comparison.png",
    labels=["Wild Type", "Mutant A", "Mutant B"],
    colors=["blue", "red", "green"]
)
```

---

### 2. `plot_md_multipanel` - Multi-Panel Plots

Create figures with multiple subplots for comprehensive analysis visualization.

**Use Cases:**
- Show RMSD, RMSF, and Rg in one figure
- Compare different properties side-by-side
- Create comprehensive analysis summaries
- Publication-quality multi-panel figures

**Parameters:**
```python
plot_md_multipanel(
    data_files: List[str],         # One data file per panel
    output_file: str,              # Output image path
    layout: str = "vertical",      # "vertical", "horizontal", or "grid"
    titles: Optional[List[str]] = None,  # Title for each panel
    xlabels: Optional[List[str]] = None,  # X-axis labels
    ylabels: Optional[List[str]] = None,  # Y-axis labels
    plot_types: Optional[List[str]] = None,  # Plot type per panel
    colors: Optional[List[str]] = None,  # Color per panel
    figsize: Optional[Tuple[int, int]] = None,  # Auto-sized if None
    dpi: int = 300,
    working_dir: Optional[str] = None
)
```

**Example:**
```python
# Vertical layout (stacked)
plot_md_multipanel(
    data_files=["rmsd.dat", "rmsf.dat", "rg.dat"],
    output_file="analysis_summary.png",
    layout="vertical",
    titles=["RMSD", "RMSF", "Radius of Gyration"],
    plot_types=["line", "bar", "line"],
    figsize=(10, 12)
)

# Grid layout for 6 properties
plot_md_multipanel(
    data_files=["prop1.dat", "prop2.dat", "prop3.dat", 
                "prop4.dat", "prop5.dat", "prop6.dat"],
    layout="grid",  # Creates 2x3 or 3x2 grid automatically
    output_file="comprehensive.png"
)
```

---

### 3. `plot_combined_data` - Multi-Column Plots

Plot multiple columns from a single data file (e.g., multiple energy terms).

**Use Cases:**
- Plot multiple energy components (Potential, Kinetic, Temperature, Pressure)
- Visualize different metrics from one analysis
- Compare related properties with shared x-axis

**Parameters:**
```python
plot_combined_data(
    data_files: List[str],         # Single data file with multiple columns
    output_file: str,
    data_columns: Optional[List[int]] = None,  # Column indices to plot
    subplot_arrangement: Optional[Tuple[int, int]] = None,  # (rows, cols)
    shared_xaxis: bool = True,     # Share x-axis across subplots
    titles: Optional[List[str]] = None,
    xlabel: Optional[str] = None,
    ylabels: Optional[List[str]] = None,
    colors: Optional[List[str]] = None,
    figsize: Tuple[int, int] = (12, 8),
    dpi: int = 300,
    working_dir: Optional[str] = None
)
```

**Example:**
```python
# Plot energy terms from GROMACS energy file
plot_combined_data(
    data_files=["energy.xvg"],
    output_file="energy_analysis.png",
    data_columns=[1, 2, 3, 4],  # Potential, Kinetic, Temp, Pressure
    subplot_arrangement=(2, 2),  # 2x2 grid
    titles=["Potential Energy", "Kinetic Energy", 
            "Temperature", "Pressure"],
    ylabels=["Energy (kJ/mol)", "Energy (kJ/mol)",
             "Temperature (K)", "Pressure (bar)"]
)
```

---

## Typical Workflow

### Basic Analysis + Plotting

```python
from agentic.analysis import (
    calculate_rmsd,
    calculate_rmsf,
    plot_md_data,
    plot_md_multipanel
)

# Step 1: Calculate analyses
rmsd_result = calculate_rmsd(
    topology_file="system.gro",
    trajectory_file="traj.xtc",
    output_file="rmsd.dat"
)

rmsf_result = calculate_rmsf(
    topology_file="system.gro",
    trajectory_file="traj.xtc",
    output_file="rmsf.dat"
)

# Step 2: Create plots
if rmsd_result["success"] and rmsf_result["success"]:
    # Multi-panel plot
    plot_md_multipanel(
        data_files=["rmsd.dat", "rmsf.dat"],
        output_file="analysis.png",
        layout="vertical",
        titles=["RMSD over Time", "RMSF per Residue"],
        plot_types=["line", "bar"]
    )
```

### Advanced: Comparison Study

```python
# Compare three different conditions
conditions = ["wildtype", "mutant_A", "mutant_B"]
rmsd_files = []

# Calculate RMSD for each
for condition in conditions:
    result = calculate_rmsd(
        topology_file=f"{condition}.gro",
        trajectory_file=f"{condition}.xtc",
        output_file=f"rmsd_{condition}.dat"
    )
    if result["success"]:
        rmsd_files.append(f"rmsd_{condition}.dat")

# Create comparison plot
plot_md_data(
    data_files=rmsd_files,
    output_file="comparison.png",
    labels=["Wild Type", "Mutant A", "Mutant B"],
    colors=["#1f77b4", "#ff7f0e", "#2ca02c"],
    xlabel="Time (ns)",
    ylabel="RMSD (Å)",
    titles=["RMSD Comparison"]
)
```

---

## Supported File Formats

The plotter tools automatically detect and parse:

- **GROMACS XVG files** (.xvg) - Standard GROMACS output format
- **Tab-delimited data** (.dat) - Simple column data
- **CSV files** (.csv) - Comma-separated values

### Data File Format

Files should contain:
- Column 1: X-axis data (time, residue number, etc.)
- Column 2+: Y-axis data (RMSD, RMSF, energy, etc.)
- Optional comment lines starting with `#` or `@`

Example:
```
# Time(ps)    RMSD(Angstrom)
0.0          0.05
100.0        1.23
200.0        1.45
...
```

---

## Output Formats

Supported output image formats:
- **PNG** (.png) - Raster graphics (good for web, presentations)
- **PDF** (.pdf) - Vector graphics (best for publications)
- **SVG** (.svg) - Vector graphics (editable in Inkscape, Illustrator)
- **EPS** (.eps) - Vector graphics (publication standard)

**Recommendation:**
- Use PNG (300 DPI) for most purposes
- Use PDF (600 DPI) for publications and print

---

## Customization Options

### Plot Types

- **"line"** - Line plot (default for time-series data)
- **"scatter"** - Scatter plot (for point data)
- **"bar"** - Bar chart (good for RMSF, per-residue data)

### Layout Options (Multi-Panel)

- **"vertical"** - Stack panels vertically (good for 2-4 panels)
- **"horizontal"** - Arrange panels horizontally (good for 2-3 panels)
- **"grid"** - Automatic grid layout (good for 4-9 panels)

### Color Options

You can specify colors as:
- Named colors: `"red"`, `"blue"`, `"green"`
- Hex codes: `"#1f77b4"`, `"#ff7f0e"`
- Matplotlib color codes: `"C0"`, `"C1"`, `"C2"`

**Colorblind-friendly palette:**
```python
colors = ["#0072B2", "#D55E00", "#009E73", "#CC79A7"]  # Blue, Orange, Green, Pink
```

### Figure Sizing

Common figure sizes (in inches):
- Single column (journal): `(3.5, 3)` or `(8, 5)`
- Double column (journal): `(7, 5)` or `(10, 6)`
- Presentation: `(10, 6)` or `(12, 8)`
- Poster: `(14, 10)` or `(16, 12)`

**Resolution (DPI):**
- Screen/web: 150 DPI
- Standard print: 300 DPI
- Publication: 600 DPI

---

## Integration with Analysis Agent

The plotting tools are automatically available to the Analysis Agent through the LLM planner:

```python
from agentic.workflow import MDWorkflow

# The agent can automatically use plotting tools when instructed
workflow = MDWorkflow(use_llm=True)

# Example instruction that triggers both analysis and plotting
state = workflow.run(
    goal="Analyze the trajectory in traj.xtc and create plots showing RMSD and RMSF"
)
```

The agent will:
1. Recognize the need for RMSD and RMSF calculations
2. Execute the appropriate analysis tools
3. Automatically call plotting tools to visualize results
4. Return paths to generated plots

---

## Error Handling

All plotting tools return a result dictionary:

```python
{
    "success": True/False,
    "output_file": "path/to/plot.png",
    "n_datasets": 2,  # or n_panels, n_plots
    "message": "Success message",
    "error": "Error message (if failed)"
}
```

Always check the `success` field:

```python
result = plot_md_data(...)
if result["success"]:
    print(f"Plot saved to: {result['output_file']}")
else:
    print(f"Plotting failed: {result['error']}")
```

---

## Tips and Best Practices

1. **Auto-detection**: Leave `xlabel` and `ylabel` as `None` to auto-detect from file headers

2. **Legends**: Automatically shown when plotting multiple datasets; customize with `labels` parameter

3. **Grid**: Grid lines automatically added with `alpha=0.3` for readability

4. **Tight layout**: Automatic layout adjustment prevents label cutoff

5. **File paths**: Use relative paths or ensure working_dir is set correctly

6. **Data quality**: Ensure data files have at least 2 columns (x and y)

7. **Memory**: Close plots after saving (handled automatically) to prevent memory issues

8. **Publication**: For publications, use:
   - PDF or EPS format
   - 600 DPI
   - Proper axis labels with units
   - Colorblind-friendly colors
   - Appropriate figure size (check journal requirements)

---

## Requirements

The plotting tools require:
- `matplotlib` - For creating plots
- `numpy` - For data handling

These are now included in the updated `environment.yml`.

To verify installation:
```bash
python -c "import matplotlib, numpy; print('✓ Plotting tools ready')"
```

---

## Examples Directory

See `examples/analysis_plotting_examples.py` for:
- 7 complete working examples
- Various use cases (comparison, comprehensive analysis, publication figures)
- Best practices demonstrations
- Commented code for learning

---

## Future Enhancements

Potential additions (let me know if you need these):
- Heatmap plotting for RMSF matrices
- 3D plots for PCA analysis
- Time-evolution animations
- Interactive plots (Plotly integration)
- Custom color maps
- Statistical overlays (mean, std, confidence intervals)
- Subplot sharing controls (x-axis, y-axis, both)

---

## Questions?

If you have questions or need help with:
- Custom plot layouts
- Specific visualization needs
- Publication figure requirements
- Integration with your workflow

Just ask! The plotting tools are designed to be flexible and extensible.
