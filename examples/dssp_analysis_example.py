"""
DSSP Secondary Structure Analysis Tool - Usage Example

This example demonstrates how to use the analyze_secondary_structure tool
to analyze protein secondary structure from MD trajectories.
"""
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.analysis.dssp_analyzer import analyze_secondary_structure


def example_basic_usage():
    """Basic DSSP analysis with minimal parameters"""
    print("\n" + "="*70)
    print("Example 1: Basic DSSP Analysis")
    print("="*70)
    
    result = analyze_secondary_structure.invoke({
        'topology_file': 'path/to/your/md.gro',
        'trajectory_file': 'path/to/your/md.xtc',
        'output_prefix': 'my_protein_dssp',
        'working_dir': './analysis_output'
    })
    
    if result['success']:
        print(f"✅ Analysis complete!")
        print(f"   Analyzed {result['n_frames']} frames")
        print(f"   Protein has {result['n_residues']} residues")
        print(f"\n   Average Secondary Structure Content:")
        for code, percentage in result['ss_percentages'].items():
            from src.analysis.dssp_analyzer import DSSP_CODE_MAP
            ss_name = DSSP_CODE_MAP[code]
            print(f"     - {ss_name:12s} ({code}): {percentage:6.2f}%")
        print(f"\n   Output files:")
        for file_type, file_path in result['output_files'].items():
            print(f"     - {file_type}: {file_path}")
    else:
        print(f"❌ Analysis failed: {result['error']}")


def example_custom_selection():
    """DSSP analysis with custom selection"""
    print("\n" + "="*70)
    print("Example 2: DSSP Analysis with Custom Selection")
    print("="*70)
    
    # Analyze only a specific protein chain or residue range
    result = analyze_secondary_structure.invoke({
        'topology_file': 'path/to/your/md.gro',
        'trajectory_file': 'path/to/your/md.xtc',
        'selection': 'protein and segid A and resid 10:100',  # Chain A, residues 10-100
        'output_prefix': 'chain_A_dssp',
        'working_dir': './analysis_output'
    })
    
    print(f"Selection: 'protein and segid A and resid 10:100'")
    print(f"Result: {result.get('n_residues', 'N/A')} residues analyzed")


def example_no_plots():
    """DSSP analysis without generating plots (data only)"""
    print("\n" + "="*70)
    print("Example 3: Data-Only Analysis (No Plots)")
    print("="*70)
    
    result = analyze_secondary_structure.invoke({
        'topology_file': 'path/to/your/md.gro',
        'trajectory_file': 'path/to/your/md.xtc',
        'output_prefix': 'dssp_data',
        'working_dir': './analysis_output',
        'create_heatmap': False,      # Skip heatmap
        'create_time_series': False,  # Skip time series plot
        'save_raw_data': True          # Keep raw data
    })
    
    print("Plots disabled - only data files will be generated")


def example_access_time_series():
    """Example showing how to access time-series data programmatically"""
    print("\n" + "="*70)
    print("Example 4: Accessing Time Series Data")
    print("="*70)
    
    result = analyze_secondary_structure.invoke({
        'topology_file': 'path/to/your/md.gro',
        'trajectory_file': 'path/to/your/md.xtc',
        'output_prefix': 'dssp_timeseries',
        'working_dir': './analysis_output'
    })
    
    if result['success']:
        # Access per-frame percentages
        helix_percentages = result['ss_percentages_per_frame']['H']  # α-helix
        sheet_percentages = result['ss_percentages_per_frame']['E']  # β-strand
        
        print(f"α-helix percentages over time:")
        print(f"  First 5 frames: {helix_percentages[:5]}")
        print(f"  Last 5 frames: {helix_percentages[-5:]}")
        
        print(f"\nβ-strand percentages over time:")
        print(f"  First 5 frames: {sheet_percentages[:5]}")
        print(f"  Last 5 frames: {sheet_percentages[-5:]}")
        
        # Check stability (from ss_stability field)
        helix_std = result['ss_stability']['H']
        print(f"\nα-helix stability (std dev): {helix_std:.2f}%")
        if helix_std < 5.0:
            print("  → Very stable helical content")
        elif helix_std < 10.0:
            print("  → Moderately stable helical content")
        else:
            print("  → Highly variable helical content")


def example_interpret_results():
    """Example showing how to interpret DSSP results"""
    print("\n" + "="*70)
    print("Example 5: Interpreting DSSP Results")
    print("="*70)
    
    # Simulated result for demonstration
    result = {
        'success': True,
        'n_frames': 1000,
        'n_residues': 250,
        'ss_percentages': {
            'H': 45.2,  # α-helix
            'E': 18.5,  # β-strand
            'T': 12.3,  # Turn
            'G': 3.1,   # 3-helix
            'I': 0.2,   # π-helix
            'B': 1.5,   # β-bridge
            'S': 4.8,   # Bend
            '-': 14.4   # Coil
        },
        'ss_stability': {
            'H': 3.2,   # Low std dev = stable
            'E': 7.8,   # Moderate std dev
            'T': 2.1,
            '-': 5.6
        }
    }
    
    print("\nInterpretation Guide:")
    print("-" * 70)
    
    helix_pct = result['ss_percentages']['H']
    sheet_pct = result['ss_percentages']['E']
    
    print(f"α-helix content: {helix_pct:.1f}%")
    if helix_pct > 40:
        print("  → Predominantly α-helical protein (e.g., myoglobin, hemoglobin)")
    elif helix_pct > 25:
        print("  → Significant α-helical content")
    else:
        print("  → Low α-helical content")
    
    print(f"\nβ-strand content: {sheet_pct:.1f}%")
    if sheet_pct > 30:
        print("  → Predominantly β-sheet protein (e.g., immunoglobulins)")
    elif sheet_pct > 15:
        print("  → Significant β-sheet content")
    else:
        print("  → Low β-sheet content")
    
    total_structured = helix_pct + sheet_pct + result['ss_percentages']['G']
    print(f"\nTotal structured content: {total_structured:.1f}%")
    print(f"Disordered/loop content: {result['ss_percentages']['-']:.1f}%")
    
    print("\nStability Analysis:")
    helix_stability = result['ss_stability']['H']
    if helix_stability < 5:
        print(f"  α-helix: Very stable (±{helix_stability:.1f}%)")
    else:
        print(f"  α-helix: Variable (±{helix_stability:.1f}%)")


def example_workflow_integration():
    """Example showing integration in workflow"""
    print("\n" + "="*70)
    print("Example 6: Workflow Integration")
    print("="*70)
    
    print("""
The analyze_secondary_structure tool is automatically available to the
analysis agent. The agent can invoke it when the user requests:

User Request Examples:
- "Analyze the secondary structure of my protein trajectory"
- "Show me how the secondary structure changes over time"
- "Create a heatmap of secondary structure for each residue"
- "What percentage of my protein is alpha helix vs beta sheet?"

The planner agent will:
1. Recognize this as a secondary structure analysis task
2. Direct the analysis agent to use analyze_secondary_structure
3. The tool will automatically:
   - Calculate DSSP for all frames
   - Generate percentage statistics
   - Create heatmap visualization
   - Create time series plots
   - Save all results
   - Return structured data for further analysis

Output Files Generated:
- {prefix}_percentages.dat     - Time series of SS percentages
- {prefix}_raw_data.dat        - Frame-by-frame DSSP assignments
- {prefix}_heatmap.png         - Residue-by-residue SS evolution
- {prefix}_timeseries.png      - SS percentage over time
- {prefix}_summary.txt         - Human-readable summary
""")


if __name__ == "__main__":
    print("="*70)
    print("DSSP Secondary Structure Analysis Tool - Usage Examples")
    print("="*70)
    
    print("\n📚 This script demonstrates various ways to use the DSSP tool.")
    print("   Note: Replace 'path/to/your/...' with actual file paths.\n")
    
    # Show all examples (with mock data, won't actually run analyses)
    example_basic_usage()
    example_custom_selection()
    example_no_plots()
    example_access_time_series()
    example_interpret_results()
    example_workflow_integration()
    
    print("\n" + "="*70)
    print("For real data analysis, ensure you have:")
    print("  1. A topology file (e.g., md.gro, md.pdb, md.tpr)")
    print("  2. A trajectory file (e.g., md.xtc, md.trr, md.dcd)")
    print("  3. MDAnalysis installed with DSSP support")
    print("="*70)
