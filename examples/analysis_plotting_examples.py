"""
Analysis Plotting Examples
==========================

Examples demonstrating how to use the MD data plotting tools for visualizing
RMSD, RMSF, Radius of Gyration, and Energy analysis results.

The analysis agent now has three powerful plotting tools:
1. plot_md_data - Single panel plots (overlay multiple datasets)
2. plot_md_multipanel - Multi-panel plots (compare different analyses)
3. plot_combined_data - Plot multiple columns from one file
"""

from agentic.analysis import (
    calculate_rmsd,
    calculate_rmsf,
    calculate_radius_of_gyration,
    analyze_energy,
    plot_md_data,
    plot_md_multipanel,
    plot_combined_data
)


# ============================================================================
# Example 1: Calculate RMSD and plot it
# ============================================================================
def example_rmsd_with_plot():
    """Calculate RMSD and create a plot."""
    
    # Step 1: Calculate RMSD
    rmsd_result = calculate_rmsd(
        topology_file="topology.gro",
        trajectory_file="trajectory.xtc",
        selection="protein and name CA",
        output_file="rmsd.dat",
        working_dir="./analysis_output"
    )
    
    if rmsd_result["success"]:
        print(f"✓ RMSD calculation complete: {rmsd_result['message']}")
        
        # Step 2: Plot RMSD
        plot_result = plot_md_data(
            data_files=["rmsd.dat"],
            output_file="rmsd_plot.png",
            plot_type="line",
            titles=["RMSD vs Time"],
            xlabel="Time (ps)",
            ylabel="RMSD (Å)",
            figsize=(10, 6),
            dpi=300,
            working_dir="./analysis_output"
        )
        
        if plot_result["success"]:
            print(f"✓ Plot created: {plot_result['output_file']}")
    

# ============================================================================
# Example 2: Calculate RMSF and create a bar plot
# ============================================================================
def example_rmsf_with_plot():
    """Calculate RMSF and create a bar plot showing per-residue flexibility."""
    
    # Step 1: Calculate RMSF
    rmsf_result = calculate_rmsf(
        topology_file="topology.gro",
        trajectory_file="trajectory.xtc",
        selection="protein and name CA",
        output_file="rmsf.dat",
        working_dir="./analysis_output"
    )
    
    if rmsf_result["success"]:
        print(f"✓ RMSF calculation complete")
        print(f"  Most flexible residue: {rmsf_result['most_flexible'][0]}")
        
        # Step 2: Plot RMSF as bar chart
        plot_result = plot_md_data(
            data_files=["rmsf.dat"],
            output_file="rmsf_plot.png",
            plot_type="bar",
            titles=["Per-Residue Flexibility (RMSF)"],
            xlabel="Residue Number",
            ylabel="RMSF (Å)",
            colors=["steelblue"],
            figsize=(12, 5),
            dpi=300,
            working_dir="./analysis_output"
        )
        
        if plot_result["success"]:
            print(f"✓ RMSF plot created: {plot_result['output_file']}")


# ============================================================================
# Example 3: Compare multiple simulations (overlay plots)
# ============================================================================
def example_compare_simulations():
    """Compare RMSD from multiple simulation runs."""
    
    # Assume we have 3 different simulation trajectories
    simulations = [
        ("sim1_topology.gro", "sim1_traj.xtc", "sim1_rmsd.dat", "Simulation 1"),
        ("sim2_topology.gro", "sim2_traj.xtc", "sim2_rmsd.dat", "Simulation 2"),
        ("sim3_topology.gro", "sim3_traj.xtc", "sim3_rmsd.dat", "Simulation 3"),
    ]
    
    data_files = []
    labels = []
    
    # Calculate RMSD for each simulation
    for topo, traj, output, label in simulations:
        result = calculate_rmsd(
            topology_file=topo,
            trajectory_file=traj,
            output_file=output,
            working_dir="./comparison"
        )
        if result["success"]:
            data_files.append(output)
            labels.append(label)
    
    # Create overlay plot comparing all simulations
    plot_result = plot_md_data(
        data_files=data_files,
        output_file="rmsd_comparison.png",
        plot_type="line",
        titles=["RMSD Comparison Across Simulations"],
        xlabel="Time (ps)",
        ylabel="RMSD (Å)",
        labels=labels,
        colors=["#1f77b4", "#ff7f0e", "#2ca02c"],  # Blue, Orange, Green
        figsize=(12, 6),
        dpi=300,
        working_dir="./comparison"
    )
    
    if plot_result["success"]:
        print(f"✓ Comparison plot with {len(data_files)} datasets created")


# ============================================================================
# Example 4: Multi-panel plot (comprehensive analysis)
# ============================================================================
def example_comprehensive_analysis():
    """Create a multi-panel figure showing RMSD, RMSF, and Rg."""
    
    topology = "system.gro"
    trajectory = "md.xtc"
    working_dir = "./comprehensive_analysis"
    
    # Step 1: Run all analyses
    print("Running analyses...")
    
    # RMSD
    rmsd_result = calculate_rmsd(
        topology_file=topology,
        trajectory_file=trajectory,
        output_file="rmsd.dat",
        working_dir=working_dir
    )
    
    # RMSF
    rmsf_result = calculate_rmsf(
        topology_file=topology,
        trajectory_file=trajectory,
        output_file="rmsf.dat",
        working_dir=working_dir
    )
    
    # Radius of Gyration
    rg_result = calculate_radius_of_gyration(
        topology_file=topology,
        trajectory_file=trajectory,
        output_file="rg.dat",
        working_dir=working_dir
    )
    
    # Step 2: Create multi-panel plot
    print("Creating multi-panel plot...")
    
    plot_result = plot_md_multipanel(
        data_files=["rmsd.dat", "rmsf.dat", "rg.dat"],
        output_file="comprehensive_analysis.png",
        layout="vertical",  # Stack vertically
        titles=[
            "RMSD - Structural Stability",
            "RMSF - Residue Flexibility", 
            "Radius of Gyration - Compactness"
        ],
        xlabels=["Time (ps)", "Residue Number", "Time (ps)"],
        ylabels=["RMSD (Å)", "RMSF (Å)", "Rg (Å)"],
        plot_types=["line", "bar", "line"],
        colors=["blue", "green", "red"],
        figsize=(10, 12),  # Tall figure for vertical layout
        dpi=300,
        working_dir=working_dir
    )
    
    if plot_result["success"]:
        print(f"✓ Comprehensive multi-panel plot created!")
        print(f"  Panels: {plot_result['n_panels']}")
        print(f"  Layout: {plot_result['layout']}")
        print(f"  File: {plot_result['output_file']}")


# ============================================================================
# Example 5: Energy analysis with multi-column plotting
# ============================================================================
def example_energy_analysis_plot():
    """Analyze energy terms and plot multiple energy components."""
    
    # Step 1: Extract energy data
    energy_result = analyze_energy(
        energy_file="md.edr",
        terms=["Potential", "Kinetic-En.", "Temperature", "Pressure"],
        output_file="energy.xvg",
        working_dir="./energy_analysis"
    )
    
    if energy_result["success"]:
        print("✓ Energy terms extracted")
        
        # Step 2: Plot all energy terms in separate panels
        plot_result = plot_combined_data(
            data_files=["energy.xvg"],
            output_file="energy_analysis.png",
            data_columns=[1, 2, 3, 4],  # Plot columns 1-4 (after x-axis)
            subplot_arrangement=(2, 2),  # 2x2 grid
            shared_xaxis=True,
            titles=[
                "Potential Energy",
                "Kinetic Energy",
                "Temperature",
                "Pressure"
            ],
            xlabel="Time (ps)",
            ylabels=[
                "Energy (kJ/mol)",
                "Energy (kJ/mol)", 
                "Temperature (K)",
                "Pressure (bar)"
            ],
            colors=["red", "blue", "orange", "green"],
            figsize=(14, 10),
            dpi=300,
            working_dir="./energy_analysis"
        )
        
        if plot_result["success"]:
            print(f"✓ Energy analysis plot with 4 panels created")


# ============================================================================
# Example 6: Grid layout for multiple properties
# ============================================================================
def example_grid_layout():
    """Create a grid layout for comparing multiple properties."""
    
    working_dir = "./grid_analysis"
    
    # Assume we have 6 different analysis outputs
    data_files = [
        "rmsd.dat",
        "rmsf.dat", 
        "rg.dat",
        "sasa.dat",
        "hbonds.dat",
        "contacts.dat"
    ]
    
    # Create a 2x3 grid plot
    plot_result = plot_md_multipanel(
        data_files=data_files,
        output_file="grid_analysis.png",
        layout="grid",  # Automatically arrange in grid
        titles=[
            "RMSD",
            "RMSF",
            "Radius of Gyration",
            "SASA",
            "H-Bonds",
            "Native Contacts"
        ],
        plot_types=["line", "bar", "line", "line", "line", "line"],
        figsize=(16, 10),  # Wide figure for grid
        dpi=300,
        working_dir=working_dir
    )
    
    if plot_result["success"]:
        print(f"✓ Grid plot with {plot_result['n_panels']} panels created")


# ============================================================================
# Example 7: Publication-quality figure
# ============================================================================
def example_publication_figure():
    """Create a publication-quality figure with custom styling."""
    
    # Calculate analyses
    working_dir = "./publication"
    
    calculate_rmsd(
        topology_file="final_system.gro",
        trajectory_file="production.xtc",
        selection="backbone",
        output_file="rmsd_backbone.dat",
        working_dir=working_dir
    )
    
    calculate_rmsd(
        topology_file="final_system.gro",
        trajectory_file="production.xtc",
        selection="protein and name CA",
        output_file="rmsd_ca.dat",
        working_dir=working_dir
    )
    
    # Create high-quality overlay plot
    plot_result = plot_md_data(
        data_files=["rmsd_backbone.dat", "rmsd_ca.dat"],
        output_file="rmsd_publication.pdf",  # PDF for publications
        plot_type="line",
        titles=None,  # No title for publication
        xlabel="Time (ns)",
        ylabel="RMSD (Å)",
        labels=["Backbone", "Cα atoms"],
        colors=["#0072B2", "#D55E00"],  # Colorblind-friendly palette
        figsize=(8, 5),  # Standard single-column figure size
        dpi=600,  # High resolution for publication
        working_dir=working_dir
    )
    
    if plot_result["success"]:
        print("✓ Publication-quality figure created (PDF, 600 DPI)")


# ============================================================================
# Run examples
# ============================================================================
if __name__ == "__main__":
    print("=" * 70)
    print("MD Analysis Plotting Examples")
    print("=" * 70)
    
    # Uncomment the examples you want to run:
    
    # example_rmsd_with_plot()
    # example_rmsf_with_plot()
    # example_compare_simulations()
    # example_comprehensive_analysis()
    # example_energy_analysis_plot()
    # example_grid_layout()
    # example_publication_figure()
    
    print("\nNote: Make sure you have the required input files before running!")
    print("See function definitions for required file names.")
