# Directory Organization for AgenticAI Workflow

## Overview

Each agent now creates files in its own subdirectory within `working_dir/` to ensure clean separation of outputs and easier debugging/inspection.

## Directory Structure

```
working_dir/
├── preprocess/          # Preprocessing agent outputs
│   ├── cleaned.pdb      # Cleaned PDB file
│   ├── topology.top     # Generated topology (if applicable)
│   └── *.log            # Processing logs
│
└── simsetup/            # Simulation setup agent outputs
    ├── processed.gro    # Initial coordinate file from topology build
    ├── boxed.gro        # After box creation
    ├── solvated.gro     # After solvation
    ├── system.gro       # Final coordinate file after ion addition
    ├── topol.top        # System topology file
    ├── minim.mdp        # Energy minimization parameters
    ├── nvt.mdp          # NVT equilibration parameters
    ├── npt.mdp          # NPT equilibration parameters
    ├── md.mdp           # Production MD parameters
    ├── ions.mdp         # Ion addition parameters
    └── *.log            # Setup logs
```

## Agent-Specific Behavior

### Preprocessing Agent
- **Directory**: `working_dir/preprocess/`
- **Creation**: Automatically created in `preprocess_node()` method
- **State Tracking**: Stores path in `state["preprocess_directory"]`
- **Outputs**:
  - `cleaned_pdb`: Cleaned and validated PDB file
  - `topology`: Optional topology file if generated
  - Processing logs

**Implementation**: [agentic/preprocess/preprocessing_agent.py](agentic/preprocess/preprocessing_agent.py)
```python
preprocess_dir = str(Path(base_working_dir) / "preprocess")
Path(preprocess_dir).mkdir(parents=True, exist_ok=True)
state["preprocess_directory"] = preprocess_dir
```

### Simulation Setup Agent
- **Directory**: `working_dir/simsetup/`
- **Creation**: Automatically created in `setup_node()` method
- **File Copying**: Copies needed files from preprocess directory via `_copy_preprocessed_files()`
- **Outputs**:
  - Coordinate files (.gro): processed, boxed, solvated, system
  - Topology file (.top)
  - MDP parameter files for all simulation phases
  - Setup logs

**Implementation**: [agentic/simsetup/setup_agent.py](agentic/simsetup/setup_agent.py)
```python
simsetup_dir = str(Path(base_working_dir) / "simsetup")
Path(simsetup_dir).mkdir(parents=True, exist_ok=True)
self._copy_preprocessed_files(state, simsetup_dir)
```

**File Copying Logic**:
```python
def _copy_preprocessed_files(self, state: MDState, simsetup_dir: str):
    """Copy preprocessed files from preprocess directory to simsetup directory."""
    preprocess_dir = state.get("preprocess_directory")
    if not preprocess_dir:
        return
        
    cleaned_pdb = state.get("cleaned_pdb", "")
    if cleaned_pdb and os.path.exists(cleaned_pdb):
        dest_pdb = os.path.join(simsetup_dir, os.path.basename(cleaned_pdb))
        shutil.copy2(cleaned_pdb, dest_pdb)
        state["cleaned_pdb"] = dest_pdb  # Update state with new path
        
    # Similar logic for topology files...
```

### HPC Agent
- **Directory**: Uses simulation setup directory outputs
- **No Subdirectory**: Does not create its own subdirectory
- **Behavior**: References files from `simsetup/` directory for job submission

### Analysis Agent
- **Directory**: May access outputs from multiple agent directories
- **No Subdirectory**: Does not create its own subdirectory currently
- **Behavior**: Reads coordinate/topology files from their respective agent directories

## Benefits

1. **Clean Separation**: Each agent's outputs are isolated, making it easier to:
   - Debug issues at specific workflow stages
   - Inspect intermediate files
   - Clean up after specific agents
   - Track data lineage

2. **State Tracking**: Directory paths stored in workflow state:
   - `state["preprocess_directory"]`: Path to preprocessing outputs
   - File paths updated when copied between directories

3. **Error Isolation**: Problems in one agent don't affect others' working directories

4. **Parallel Development**: Multiple developers can work on different agents without file conflicts

## Migration Notes

### Old Behavior
All agents wrote to the same `working_dir/` directory, causing:
- File naming conflicts
- Unclear data provenance
- Difficult debugging (mixed outputs)

### New Behavior
Each agent has its own subdirectory with explicit file copying between stages.

### Breaking Changes
- File paths in state now point to agent-specific subdirectories
- Tools must use agent-specific working directory
- File copying required when one agent needs another's outputs

## Future Extensions

### Analysis Agent
Could create `working_dir/analysis/` for:
- Computed metrics (RMSD, RMSF)
- Generated plots
- Analysis reports

### HPC Agent
Could create `working_dir/hpc/` for:
- SLURM job scripts
- Job submission logs
- Status tracking files

## Implementation Checklist

When adding a new agent that creates files:

- [ ] Create agent-specific subdirectory in workflow node:
  ```python
  agent_dir = str(Path(base_working_dir) / "agent_name")
  Path(agent_dir).mkdir(parents=True, exist_ok=True)
  ```

- [ ] Store directory path in state:
  ```python
  state["agent_name_directory"] = agent_dir
  ```

- [ ] Update all file operations to use agent directory:
  ```python
  output_file = os.path.join(agent_dir, "output.txt")
  ```

- [ ] Add file copying method if agent needs inputs from other agents:
  ```python
  def _copy_required_files(self, state, agent_dir):
      source_dir = state.get("source_agent_directory")
      # Copy files with shutil.copy2()
  ```

- [ ] Update state with new file paths after copying:
  ```python
  state["file_path"] = dest_path
  ```

## Testing

Test directory organization with:
```bash
python run_agenticAIWork.py --goal "Test workflow with directory separation" --no-human-loop
ls -R working_dir/  # Verify directory structure
```

Expected output:
```
working_dir/:
preprocess/  simsetup/

working_dir/preprocess/:
cleaned.pdb  preprocessing.log

working_dir/simsetup/:
processed.gro  boxed.gro  solvated.gro  system.gro  topol.top  minim.mdp  nvt.mdp  npt.mdp  md.mdp  ions.mdp
```
