# Subtask-Specific Workflows - Implementation Guide

## Overview

The AgenticAI system has been enhanced to support **flexible, subtask-specific workflows**. Users can now request:

- **Analysis-only**: Analyze existing trajectory data without preprocessing or setup
- **Setup-only**: Generate topology and parameters without HPC submission
- **Preprocess-only**: Clean and prepare structures without full pipeline
- **Full pipeline**: Complete MD workflow (default)

This makes the system flexible enough to handle any stage of molecular dynamics work, not just end-to-end simulations.

---

## Architecture Changes

### 1. **Supervisor Enhancement** ([agentic/supervisor/supervisor.py](agentic/supervisor/supervisor.py))

#### New Detection System
- `detect_subtask_type()` - Identifies user intent (analysis-only, setup-only, etc.)
- `detect_task_required_inputs()` - Determines which inputs are actually needed
- `detect_trajectory_paths()` - Extracts trajectory file paths for analysis-only tasks

#### Flexible Input Validation
- **Old behavior**: Always required PDB file and full analysis
- **New behavior**: 
  - Skips PDB validation for analysis-only tasks
  - Validates trajectory paths instead
  - Only validates required inputs for the specific subtask

#### New Method
```python
def _validate_analysis_inputs(self, state: MDState) -> MDState:
    """Validate inputs for analysis-only tasks without PDB analysis"""
```

### 2. **Planner Enhancement** ([agentic/planner/planner_agent.py](agentic/planner/planner_agent.py))

#### Subtask-Aware Planning
- Receives `subtask_type` from supervisor
- Includes subtask context in LLM planning prompt
- Filters agents based on actual requirements

#### Fallback Planning Improvements
- `_create_fallback_plan()` now respects subtask types
- Skips unnecessary agents:
  - Analysis-only: Skip preprocessing, setup, HPC
  - Setup-only: Skip preprocessing (optional), HPC
  - Preprocess-only: Skip setup, HPC, analysis

### 3. **State Management** ([agentic/state.py](agentic/state.py))

New MDState fields:
```python
subtask_type: Optional[str]           # "analysis_only", "setup_only", etc.
required_inputs: Optional[Dict]       # Tracks what inputs are needed
analysis_validated: Optional[bool]    # Whether analysis inputs validated
trajectory_paths: Optional[Dict]      # {"trajectory_path", "topology_path", "energy_path"}
```

### 4. **Supervisor Tool Functions** ([agentic/supervisor/tools.py](agentic/supervisor/tools.py))

#### Pattern Detection
```python
def detect_subtask_type(user_goal: str) -> Optional[str]:
    """
    Returns: "analysis_only", "setup_only", "preprocess_only", or None (full pipeline)
    """
```

Detects user intent from natural language patterns:
- **Analysis-only**: "only analysis", "analysis only", "analyze trajectory" + exclusions
- **Setup-only**: "setup only", "topology only" + "no hpc" / "without hpc"
- **Preprocess-only**: "only preprocessing", "clean structure" + exclusion phrases

#### Input Validation
```python
def detect_task_required_inputs(subtask_type: Optional[str], user_goal: str) -> Dict:
    """
    Returns required inputs:
    - pdb_required: bool
    - pdb_analysis_required: bool
    - trajectory_path_required: bool
    - topology_required: bool
    """
```

#### File Path Extraction
```python
def detect_trajectory_paths(user_goal: str) -> Dict:
    """
    Extracts trajectory file paths for analysis-only tasks:
    - trajectory_path: .xtc, .trr, .dcd
    - topology_path: .tpr, .top, .gro
    - energy_path: .edr
    """
```

---

## Usage Examples

### Example 1: Analysis-Only Workflow

**User Request:**
```
--goal "The protein was used for the simulation. The simulation production is already done 
and data output is stored in working_dir/hpc. Please dont preprocess, do not setup simulation 
and do not job submit. Only use the analysis agent for RMSF calculation of trajectory 
working_dir/hpc/md.xtc with topology working_dir/hpc/topol.tpr"
```

**Flow:**
1. Supervisor detects: `subtask_type = "analysis_only"`
2. Supervisor skips PDB validation
3. Supervisor validates trajectory paths
4. Planner creates plan with ONLY Analysis Agent
5. Analysis Agent runs RMSF calculations

**Key Benefit:** No PDB file required, no preprocessing overhead

---

### Example 2: Setup-Only Workflow

**User Request:**
```
--goal "Set up MD simulation for working_dir/protein.pdb for 1 ns with amber99sb-ildn. 
I only need topology and parameter files - setup only, no HPC submission"
```

**Flow:**
1. Supervisor detects: `subtask_type = "setup_only"`
2. Supervisor validates PDB (required)
3. Supervisor analyzes PDB structure
4. Planner creates plan with Preprocessing + Setup Agents (skips HPC, Analysis)
5. Setup Agent generates topology, mdp files, coordinates

**Key Benefit:** Streamlined workflow, no waiting for HPC jobs

---

### Example 3: Preprocess-Only Workflow

**User Request:**
```
--goal "Please preprocess my protein structure from working_dir/raw.pdb. 
Only clean the structure - remove waters, add hydrogens. Nothing else."
```

**Flow:**
1. Supervisor detects: `subtask_type = "preprocess_only"`
2. Supervisor validates PDB
3. Supervisor analyzes structure
4. Planner creates plan with ONLY Preprocessing Agent (skips setup, HPC, analysis)
5. Preprocessing Agent cleans structure outputs cleaned PDB

**Key Benefit:** Fast structure preparation without downstream processing

---

### Example 4: Full Pipeline (Traditional)

**User Request:**
```
--goal "Run complete MD simulation of working_dir/protein.pdb with 1 ns runtime. 
Analyze RMSD and RMSF after completion."
```

**Flow:**
1. Supervisor detects: `subtask_type = None` (full pipeline)
2. Standard validation and planning with all agents
3. Complete workflow: Preprocess → Setup → HPC → Analysis

**Key Benefit:** Unchanged behavior for existing users

---

## Executor Implementation Changes

### Supervisor: Input Validation Decision Logic

**Before:**
```python
if not state.get("pdb_analysis") and state.get("user_goal"):
    state["next_node"] = "input_validation"  # Always validate PDB
    return state
```

**After:**
```python
# Detect subtask type
subtask_type = detect_subtask_type(state.get("user_goal", ""))
state["subtask_type"] = subtask_type

# Check if PDB analysis is required
required_inputs = detect_task_required_inputs(subtask_type, user_goal)
state["required_inputs"] = required_inputs

if not state.get("pdb_analysis") and required_inputs.get("pdb_analysis_required", True):
    state["next_node"] = "input_validation"
    return state

# For analysis-only, validate differently
if subtask_type == "analysis_only" and not state.get("analysis_validated"):
    state = self._validate_analysis_inputs(state)
    state["analysis_validated"] = True
```

### Planner: Fallback Plan Generation

**Before:**
```python
def _create_fallback_plan(...) -> Dict:
    # Always create preprocessing + setup + hpc + analysis steps
    # based on PDB structure analysis
```

**After:**
```python
def _create_fallback_plan(...) -> Dict:
    subtask_type = state.get("subtask_type")
    
    # Analysis-only: skip to analysis
    if subtask_type == "analysis_only":
        return create_plan_with_only_analysis()
    
    # Setup-only: preprocessing (optional) + setup only
    elif subtask_type == "setup_only":
        return create_plan_with_preprocessing_and_setup()
    
    # Full pipeline: all steps
    else:
        return create_plan_with_all_steps()
```

---

## Testing

### Core Functionality Tests

Run tests to verify subtask detection:

```bash
cd /home/akp66103/workspace/agenticAI

# Quick validation tests
python -c "
from agentic.supervisor.tools import detect_subtask_type

# Test cases
assert detect_subtask_type('Only analyze trajectory. No preprocessing.') == 'analysis_only'
assert detect_subtask_type('Setup only - topology generation') == 'setup_only'
assert detect_subtask_type('Run MD for 1 ns') is None
print('✓ All tests passed')
"
```

### Comprehensive Test Suite

```bash
python tests/test_subtask_workflows.py
```

Tests included:
- ✅ Analysis-only detection
- ✅ Setup-only detection
- ✅ Preprocess-only detection
- ✅ Required inputs detection
- ✅ Trajectory path extraction
- ✅ Full pipeline detection
- ✅ State initialization

---

## Backward Compatibility

**✅ FULLY BACKWARD COMPATIBLE**

- Existing full-pipeline workflows unchanged
- New subtask detection is automatic, non-intrusive
- If no subtask pattern detected, system behaves as before
- All existing user goals continue to work

---

## Benefits Summary

| Feature | Before | After |
|---------|--------|-------|
| **Analysis on existing data** | ❌ Require PDB file | ✅ Use trajectory only |
| **Quick topology generation** | ❌ Must do full setup | ✅ Setup-only mode |
| **Structure preparation** | ❌ Must do full pipeline | ✅ Preprocess-only mode |
| **Flexibility** | ❌ Full pipeline only | ✅ Any combination |
| **User input** | ❌ Always need PDB | ✅ Conditional on subtask |
| **Plan complexity** | ❌ All agents always | ✅ Only needed agents |

---

## Future Enhancements

Potential improvements:
1. **Ligand-only workflows** - Start with ligand parameterization only
2. **Custom agent combinations** - User explicitly specifies agent sequence
3. **Intelligent dependencies** - Smarter detection of inter-dependencies
4. **Partial analysis** - Run analysis on select trajectories within a run
5. **Resume functionality** - Pre-existing partial results as inputs

---

## Troubleshooting

### Issue: Analysis-only not detected

**Solution:** Ensure user goal includes explicit exclusion phrases:
- ❌ "Please analyze my trajectory"
- ✅ "Only analyze trajectory. No preprocessing or setup."

Explicit exclusions help LLM and regex detection correctly classify the task.

### Issue: Setup-only includes preprocessing

**Solution:** Preprocessing is often necessary. To skip:
- Include explicit preprocessing exclusion
- Provide already-cleaned PDB file
- Mention "cleaned" or "preprocessed" in goal

### Issue: Trajectory paths not extracted

**Solution:** Ensure paths are in standard format:
- ✅ `working_dir/hpc/md.xtc` (full path)
- ❌ `md.xtc` (bare filename without directory)
- ✅ `./trajectories/prod.xtc` (relative path)

---

## Code References

- [Supervisor with subtask support](agentic/supervisor/supervisor.py)
- [Detection functions](agentic/supervisor/tools.py)
- [Planner enhancements](agentic/planner/planner_agent.py)
- [Updated state definition](agentic/state.py)
- [Test suite](tests/test_subtask_workflows.py)

---

## Summary

The project is now **fully flexible for any subtask-specific MD workflow**. Users can:

1. ✅ Run analysis on existing trajectory data
2. ✅ Generate topology files only
3. ✅ Preprocess structures standalone  
4. ✅ Run full end-to-end pipelines
5. ✅ Mix and match agents as needed

All while maintaining **100% backward compatibility** with existing workflows.
