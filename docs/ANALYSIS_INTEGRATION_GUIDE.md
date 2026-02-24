# Quick Integration Guide: Analysis Agent

## Adding Analysis to Your Workflow

The Analysis Agent is now ready to be integrated into your MD workflow. Here's how to use it:

## Option 1: Standalone Usage

### Basic Analysis
```python
from agentic.analysis import MDAnalysisAgent, run_complete_analysis
from agentic.llm import LLMClient

# Quick analysis of trajectory
results = run_complete_analysis(
    topology_file="system.gro",
    trajectory_file="md.xtc",
    energy_file="energy.edr",
    working_dir="./analysis_output",
    analyses=["rmsd", "rmsf", "gyration", "energy"]
)

print(results["summary"])
for analysis, data in results["results"].items():
    print(f"{analysis}: {data['message']}")
```

### Using Agent Class
```python
from agentic.analysis import MDAnalysisAgent
from agentic.llm import LLMClient
from agentic.state import MDState

# Initialize agent
llm = LLMClient("gpt-oss:20b")
agent = MDAnalysisAgent(llm_client=llm)

# Create state
state = MDState(
    goal="Analyze MD simulation stability",
    trajectory_path="./working_dir/hpc/results/md.xtc",
    topology_file="./working_dir/hpc/results/system.gro",
    energy_file="./working_dir/hpc/results/energy.edr",
    analysis_action="full_analysis",
    errors=[],
    warnings=[],
    next_node="analysis"
)

# Run analysis
result_state = agent.analysis_node(state)

# Check results
if result_state["analysis_results"]["success"]:
    print(result_state["analysis_results"]["report"])
```

## Option 2: Workflow Integration

### Update Workflow to Include Analysis

In your `agentic/workflow.py` or wherever you define the workflow graph:

```python
from agentic.analysis import MDAnalysisAgent

class MDWorkflow:
    def __init__(self, llm_client: LLMClient, ...):
        # ... existing initialization ...
        
        # Add analysis agent
        self.analysis_agent = MDAnalysisAgent(llm_client=llm_client)
    
    def build_graph(self):
        # ... existing graph building ...
        
        # Add analysis node
        workflow.add_node("analysis", self.analysis_agent.analysis_node)
        
        # Add edges from HPC to analysis
        workflow.add_edge("hpc", "analysis")
        
        # Analysis routes back to supervisor
        # (already handled in analysis_agent.py)
```

### Supervisor Routing

Update your supervisor to route to analysis after HPC completion:

```python
def supervisor_node(state: MDState) -> MDState:
    """Supervisor routing logic"""
    
    # ... existing logic ...
    
    # After HPC completes successfully
    if state.get("hpc_status") == "completed":
        state["next_node"] = "analysis"
        state["analysis_action"] = "full_analysis"
        return state
    
    # ... rest of logic ...
```

## Option 3: Command-Line Integration

### Update run_agenticAIWork.py

```python
# Add analysis argument
parser.add_argument(
    "--run-analysis",
    action="store_true",
    help="Run trajectory analysis after simulation"
)

parser.add_argument(
    "--analyses",
    nargs="+",
    default=["rmsd", "rmsf", "gyration"],
    choices=["rmsd", "rmsf", "gyration", "energy", "metrics"],
    help="Specific analyses to perform"
)

# In main execution
if args.run_analysis:
    state["analysis_action"] = "full_analysis"
    state["requested_analyses"] = args.analyses
```

## Analysis Actions

Set `state["analysis_action"]` to control behavior:

- `"full_analysis"`: Complete workflow with all selected analyses
- `"plan_only"`: Create analysis plan without execution
- `"rmsd_only"`: Calculate only RMSD
- `"rmsf_only"`: Calculate only RMSF
- `"gyration_only"`: Calculate only radius of gyration
- `"energy_only"`: Analyze energy terms only

## Common Workflows

### 1. Post-Simulation Analysis
```python
# After HPC simulation completes
state["next_node"] = "analysis"
state["analysis_action"] = "full_analysis"
state["trajectory_path"] = hpc_results_dir + "/md.xtc"
state["topology_file"] = hpc_results_dir + "/system.gro"
state["energy_file"] = hpc_results_dir + "/energy.edr"
```

### 2. Custom Analysis Selection
```python
# Analyze only stability metrics
state["analysis_action"] = "full_analysis"
state["requested_analyses"] = ["rmsd", "gyration"]
```

### 3. Quick RMSD Check
```python
# Fast stability check
state["analysis_action"] = "rmsd_only"
```

## Accessing Results

### From State
```python
results = state["analysis_results"]

# Overall summary
print(results["summary"])

# Individual analysis results
rmsd_data = results["results"]["rmsd"]
print(f"Mean RMSD: {rmsd_data['mean_rmsd']:.2f} Å")

# Generated report
print(results["report"])  # Markdown format

# Output files
output_dir = results["output_directory"]
```

### Reading Output Files
```python
import pandas as pd

# Read RMSD data
rmsd_df = pd.read_csv(
    "working_dir/analysis/rmsd.dat",
    sep="\t",
    comment="#",
    names=["Frame", "Time_ps", "RMSD_A"]
)

# Read RMSF data
rmsf_df = pd.read_csv(
    "working_dir/analysis/rmsf.dat",
    sep="\t",
    comment="#",
    names=["Residue_ID", "Residue_Name", "RMSF_A"]
)
```

## Configuration

### Custom Working Directory
```python
agent = MDAnalysisAgent(
    llm_client=llm,
    config_path="custom_config.yaml"
)
```

### Modify Analysis Settings
Edit `agentic/analysis/config.yaml`:

```yaml
workflow:
  default_analyses: ["rmsd", "rmsf"]  # Change defaults
  generate_plots: true  # Enable/disable plots

tools:
  calculate_rmsd:
    defaults:
      selection: "protein and name CA"  # Change atom selection
      reference_frame: 0
```

## Error Handling

```python
# Check for errors
if state["errors"]:
    print("Errors occurred:")
    for error in state["errors"]:
        print(f"  - {error}")

# Check for warnings
if state["warnings"]:
    print("Warnings:")
    for warning in state["warnings"]:
        print(f"  - {warning}")

# Check analysis status
if state["analysis_results"].get("success"):
    print("Analysis completed successfully!")
else:
    print("Analysis had failures")
    print(state["analysis_results"].get("errors"))
```

## Example: Complete Workflow

```python
from agentic.workflow import MDWorkflow
from agentic.llm import LLMClient
from agentic.state import MDState

# Initialize workflow with analysis
llm = LLMClient("gpt-oss:20b")
workflow = MDWorkflow(llm_client=llm, enable_analysis=True)

# Run complete workflow
initial_state = MDState(
    goal="Run MD simulation and analyze stability",
    pdb_files=["protein.pdb"],
    run_analysis=True,
    analysis_types=["rmsd", "rmsf", "gyration"],
    errors=[],
    warnings=[]
)

# Execute
final_state = workflow.run(initial_state)

# Get analysis report
report = final_state["analysis_results"]["report"]
print(report)

# Save report to file
with open("md_analysis_report.md", "w") as f:
    f.write(report)
```

## Troubleshooting

### Issue: "Trajectory file not found"
**Solution**: Ensure HPC results are downloaded before analysis
```python
# Check files before analysis
import os
if not os.path.exists(state["trajectory_path"]):
    print("Downloading HPC results first...")
    # Download from HPC
```

### Issue: "MDAnalysis not available"
**Solution**: Agent falls back to GROMACS automatically, no action needed
```bash
# Optional: Install MDAnalysis for better performance
pip install MDAnalysis
```

### Issue: "Selection returned no atoms"
**Solution**: Use valid MDAnalysis selection syntax
```python
# Valid selections:
"protein and name CA"  # C-alpha atoms
"backbone"             # Backbone atoms
"protein"              # All protein atoms
"resid 1-50"          # Specific residues
```

## Performance Tips

1. **Large trajectories**: Use stride or sampling
2. **Multiple analyses**: Tools run sequentially (can parallelize manually)
3. **Memory**: RMSF loads full trajectory into memory
4. **Storage**: Use fast SSD for working_dir

## Next Steps

1. ✅ Analysis agent is ready to use
2. Integrate into your workflow (see examples above)
3. Test with real trajectory data
4. Customize config.yaml for your needs
5. Extend with custom analyses as needed

For detailed documentation, see:
- [docs/ANALYSIS_AGENT.md](ANALYSIS_AGENT.md)
- [docs/ANALYSIS_AGENT_IMPLEMENTATION.md](ANALYSIS_AGENT_IMPLEMENTATION.md)
