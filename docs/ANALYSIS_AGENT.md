# Analysis Agent Documentation

## Overview

The Analysis Agent is a sophisticated component of the AgenticAI MD workflow system that performs structural and dynamic analysis of molecular dynamics simulation trajectories. It follows the same architectural patterns as the HPC and Setup agents, featuring:

- **LLM-powered planning**: Intelligent analysis selection based on user goals
- **Modular tool architecture**: Core tools in `src/analysis/`, wrapped in `agentic/analysis/tools.py`
- **Pydantic validation**: Strong typing with `schemas.py`
- **Graceful fallbacks**: Works with both MDAnalysis and GROMACS tools

## Architecture

```
agentic/analysis/
├── __init__.py          # Package exports
├── analysis_agent.py    # Main agent class (MDAnalysisAgent)
├── config.yaml          # Agent configuration
├── schemas.py           # Pydantic validation schemas
└── tools.py             # Tool wrappers and executor

src/analysis/
├── __init__.py
├── rmsd_calculator.py   # RMSD calculation
├── rmsf_calculator.py   # RMSF calculation
├── gyration_calculator.py # Radius of gyration
└── energy_analyzer.py   # Energy analysis
```

## Features

### Implemented Analyses

1. **RMSD (Root Mean Square Deviation)**
   - Measures structural stability over time
   - Supports custom atom selections
   - Configurable reference frame
   - Output: mean, std, min, max RMSD values

2. **RMSF (Root Mean Square Fluctuation)**
   - Per-residue flexibility analysis
   - Identifies rigid vs. flexible regions
   - Highlights most/least flexible residues
   - Output: per-residue RMSF data

3. **Radius of Gyration**
   - Protein compactness measurement
   - Detects folding/unfolding events
   - Tracks conformational changes
   - Output: Rg time series and statistics

4. **Energy Analysis**
   - Extracts thermodynamic properties
   - Analyzes potential, kinetic energy
   - Monitors temperature, pressure
   - Output: energy term statistics

5. **Trajectory Metrics**
   - Basic trajectory information
   - Frame count, time range
   - File size statistics

## Usage

### Basic Usage

```python
from agentic.analysis import MDAnalysisAgent
from agentic.llm import LLMClient
from agentic.state import MDState

# Initialize agent
llm = LLMClient("gpt-oss:20b")
agent = MDAnalysisAgent(llm_client=llm)

# Create state with trajectory files
state = MDState(
    goal="Analyze MD simulation",
    trajectory_path="md.xtc",
    topology_file="system.gro",
    energy_file="energy.edr",
    analysis_action="full_analysis",
    errors=[],
    warnings=[],
    next_node="analysis"
)

# Run analysis
result_state = agent.analysis_node(state)

# Access results
results = result_state["analysis_results"]
print(results["summary"])
```

### Using Individual Tools

```python
from agentic.analysis.tools import calculate_rmsd, calculate_rmsf

# Calculate RMSD
rmsd_result = calculate_rmsd(
    topology_file="system.gro",
    trajectory_file="md.xtc",
    selection="protein and name CA",
    output_file="rmsd.dat",
    working_dir="./analysis"
)

print(f"Mean RMSD: {rmsd_result['mean_rmsd']:.2f} Å")

# Calculate RMSF
rmsf_result = calculate_rmsf(
    topology_file="system.gro",
    trajectory_file="md.xtc",
    selection="protein and name CA",
    output_file="rmsf.dat"
)

print(f"Mean RMSF: {rmsf_result['mean_rmsf']:.2f} Å")
```

### Using AnalysisToolExecutor

```python
from agentic.analysis.tools import AnalysisToolExecutor

# Initialize executor
executor = AnalysisToolExecutor(config={
    "agent": {"working_directory": "./analysis_output"}
})

# Run complete workflow
results = executor.execute_workflow(
    topology_file="system.gro",
    trajectory_file="md.xtc",
    energy_file="energy.edr",
    analyses=["rmsd", "rmsf", "gyration", "energy"]
)

print(results["summary"])
for analysis, result in results["results"].items():
    if result["success"]:
        print(f"{analysis}: {result['message']}")
```

## Configuration

The agent is configured via [config.yaml](config.yaml):

### Key Configuration Sections

1. **Agent Settings**
```yaml
agent:
  name: "AnalysisAgent"
  working_directory: "working_dir/analysis"
  max_tool_retries: 2
  fail_fast: false
```

2. **Workflow Defaults**
```yaml
workflow:
  default_analyses: ["rmsd", "rmsf", "gyration", "energy"]
  generate_plots: true
```

3. **Tool Settings**
```yaml
tools:
  calculate_rmsd:
    defaults:
      selection: "protein and name CA"
      reference_frame: 0
```

4. **Selection Presets**
```yaml
selection_presets:
  protein_ca:
    selection: "protein and name CA"
    description: "Protein C-alpha atoms"
```

## Analysis Actions

The agent supports several action modes:

- `full_analysis`: Complete workflow with all analyses
- `plan_only`: Create analysis plan without execution
- `rmsd_only`: Calculate only RMSD
- `rmsf_only`: Calculate only RMSF
- `energy_only`: Analyze energy terms only

Set via `state["analysis_action"]`.

## Output Format

### Result Structure

```python
{
    "success": True,
    "analyses_completed": ["rmsd", "rmsf"],
    "results": {
        "rmsd": {
            "success": True,
            "mean_rmsd": 2.34,
            "std_rmsd": 0.45,
            "n_frames": 5000,
            "message": "RMSD calculation complete"
        },
        "rmsf": {
            "success": True,
            "mean_rmsf": 1.23,
            "most_flexible": [...],
            "least_flexible": [...]
        }
    },
    "output_directory": "./working_dir/analysis",
    "summary": "Completed 2/2 analyses",
    "report": "# MD Trajectory Analysis Report\n..."
}
```

### Generated Files

- `rmsd.dat` - RMSD time series
- `rmsf.dat` - Per-residue RMSF data
- `gyrate.dat` - Radius of gyration data
- `energy.xvg` - Energy terms
- `analysis_report.md` - Comprehensive markdown report

## Schemas

All inputs/outputs are validated using Pydantic schemas:

```python
from agentic.analysis.schemas import (
    RMSDAnalysisInput,
    RMSFAnalysisInput,
    AnalysisWorkflowInput
)

# Validate input
input_data = RMSDAnalysisInput(
    topology_file="system.gro",
    trajectory_file="md.xtc",
    selection="protein and name CA"
)
```

Available schemas:
- `RMSDAnalysisInput` / `RMSDResult`
- `RMSFAnalysisInput` / `RMSFResult`
- `GyrationAnalysisInput` / `GyrationResult`
- `EnergyAnalysisInput` / `EnergyResult`
- `AnalysisWorkflowInput` / `AnalysisWorkflowOutput`

## Dependencies

### Required
- Python 3.8+
- GROMACS (fallback for analysis tools)
- PyYAML
- Pydantic

### Optional (Enhanced Features)
- MDAnalysis (recommended for trajectory analysis)
- NumPy (for statistical calculations)
- Matplotlib (for plot generation)

### Graceful Fallbacks

When MDAnalysis is not available, the agent automatically falls back to GROMACS command-line tools:
- `gmx rms` for RMSD
- `gmx rmsf` for RMSF
- `gmx gyrate` for radius of gyration
- `gmx energy` for energy analysis

## Integration with Workflow

The Analysis Agent integrates seamlessly with the AgenticAI workflow:

```python
from agentic.workflow import MDWorkflow

# The workflow automatically calls analysis after HPC completion
workflow = MDWorkflow(...)
result = workflow.run(goal="Run and analyze MD simulation")

# Analysis results are in the state
analysis_results = result["analysis_results"]
```

## Testing

Run tests with:

```bash
python tests/test_analysis_agent.py
```

Tests cover:
- Schema validation
- Tool imports and execution
- Agent initialization
- Configuration loading
- Directory structure

## Extending the Agent

### Adding New Analysis Tools

1. **Implement tool in `src/analysis/`**:
```python
# src/analysis/new_analysis.py
from langchain.tools import tool

@tool
def calculate_new_metric(topology_file: str, trajectory_file: str) -> Dict[str, Any]:
    """New analysis tool"""
    # Implementation
    return {"success": True, "result": ...}
```

2. **Import in `agentic/analysis/tools.py`**:
```python
from src.analysis.new_analysis import calculate_new_metric
```

3. **Add to AnalysisToolExecutor**:
```python
self.tools = {
    ...,
    "calculate_new_metric": calculate_new_metric
}
```

4. **Define schema in `schemas.py`**:
```python
class NewAnalysisInput(BaseModel):
    topology_file: str
    trajectory_file: str
```

5. **Update `config.yaml`**:
```yaml
tools:
  calculate_new_metric:
    description: "New analysis"
    defaults: {...}
```

## Interpretation Guidelines

The config includes interpretation thresholds:

### RMSD
- < 1.5 Å: Excellent stability
- 1.5-3.0 Å: Good stability
- 3.0-5.0 Å: Moderate changes
- > 5.0 Å: Significant drift

### RMSF
- < 1.0 Å: Rigid region
- 1.0-3.0 Å: Moderate flexibility
- > 3.0 Å: High flexibility

### Radius of Gyration
- std/mean < 0.05: Stable structure
- 0.05-0.10: Some changes
- > 0.10: Significant changes

## Troubleshooting

### Common Issues

1. **"Trajectory file not found"**
   - Check `state["trajectory_path"]` is set
   - Verify file exists in HPC results directory

2. **"MDAnalysis not available"**
   - Agent falls back to GROMACS tools automatically
   - Install MDAnalysis for better performance: `pip install MDAnalysis`

3. **"No atoms selected"**
   - Check selection syntax (MDAnalysis format)
   - Common: `"protein and name CA"`, `"backbone"`, `"protein"`

4. **Analysis fails but no error**
   - Check `state["errors"]` and `state["warnings"]`
   - Enable debug logging: `logging.basicConfig(level=logging.DEBUG)`

## Performance Considerations

- **Large trajectories**: Use stride in MDAnalysis or GROMACS `-skip` flag
- **Memory usage**: RMSF requires loading full trajectory into memory
- **I/O optimization**: Store outputs in fast storage (SSD)
- **Parallel analysis**: Tools are independent and can be parallelized

## Future Enhancements

Planned features for scalability:

1. **Distance Analysis**
   - Protein-ligand distances
   - Salt bridge analysis
   - Hydrogen bond tracking

2. **Clustering Analysis**
   - Conformational clustering
   - Representative structures

3. **PCA (Principal Component Analysis)**
   - Essential dynamics
   - Collective motions

4. **Binding Free Energy**
   - MM-PBSA/MM-GBSA
   - Interaction energies

5. **Visualization**
   - Automated plot generation
   - Interactive dashboards
   - PyMOL/VMD script generation

## References

- MDAnalysis: https://www.mdanalysis.org/
- GROMACS manual: https://manual.gromacs.org/
- Pydantic documentation: https://pydantic-docs.helpmanual.io/
