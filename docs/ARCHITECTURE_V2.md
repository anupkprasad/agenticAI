# AgenticAI Architecture V2: Intelligent Supervisor-Planner-Agent System

## Overview

This document describes the enhanced architecture that introduces **PDB structure analysis**, **user intent parsing**, and **dependency-aware planning** into the MD workflow.

## Architecture Components

### 1. **Supervisor** (Enhanced)
Location: `agentic/supervisor.py`

**Responsibilities:**
- **Phase 1: Input Validation & Analysis**
  - Extract PDB file path from user prompt
  - Analyze PDB structure using `src/utils/pdb_analyzer.py`
  - Detect components (protein, ligand, water, ions, chains)
  - Parse user intent and component selection
  - Validate feasibility of user requests
  - Create structured prompt for planner

- **Phase 2: Orchestration**
  - Collaborate with planner to create execution plan
  - Route tasks to field agents step-by-step
  - Track execution progress (`current_step`)
  - Handle dependencies between steps

**New Methods:**
```python
def input_validation_node(state: MDState) -> MDState:
    """Comprehensive validation with PDB analysis"""
    
def _parse_component_selection(user_goal, analysis) -> Dict:
    """Parse user intent (e.g., 'protein only', 'without ligand')"""
    
def _validate_feasibility(user_goal, analysis, selection) -> Dict:
    """Check if request is feasible given PDB contents"""
    
def _create_structured_prompt(user_goal, analysis, selection, validation) -> str:
    """Create high-level structured prompt for planner"""
```

### 2. **Planner** (Enhanced)
Location: `agentic/planner/planner_agent.py`

**Responsibilities:**
- Generate dependency-aware execution plans
- Define clear inputs/outputs for each step
- Specify field-specific agents for each task
- Consider PDB analysis results in planning

**New Methods:**
```python
def _create_plan_from_analysis(
    structured_prompt, 
    pdb_path, 
    pdb_analysis, 
    component_selection, 
    state
) -> Dict:
    """Create detailed plan based on PDB analysis"""
```

**Plan Structure:**
```python
{
    "title": "MD Workflow: ...",
    "summary": "...",
    "method": "analysis_based",
    "steps": [
        {
            "step_number": 1,
            "name": "Step name",
            "agent": "preprocessing_agent",
            "description": "Detailed description",
            "inputs": {
                "raw_pdb": "path/to/file.pdb",
                "component_selection": {...},
                "tasks": [...]
            },
            "expected_outputs": ["cleaned_pdb", "preprocessing_report"],
            "dependencies": [],  # Which steps must complete first
            "tools": ["tool1", "tool2"],
            "type": "automated"
        },
        # ... more steps
    ]
}
```

### 3. **State Management** (Enhanced)
Location: `agentic/state.py`

**New State Fields:**
```python
class MDState(TypedDict):
    # PDB Analysis (from supervisor validation)
    pdb_analysis: Optional[Dict[str, Any]]  # PDB structure analysis
    component_selection: Optional[Dict[str, Any]]  # User component selection
    structured_prompt: Optional[str]  # Structured prompt for planner
    
    # Planning (enhanced)
    current_step: Optional[int]  # Current step being executed (0-indexed)
```

### 4. **PDB Analyzer** (New Utility)
Location: `src/utils/pdb_analyzer.py`

**Functionality:**
- Comprehensive PDB structure analysis using MDAnalysis
- Detects:
  - Proteins (chains, sequences, residue counts)
  - Ligands (residue names, atom counts)
  - Water molecules
  - Ions
  - Missing hydrogens
  - Alternate locations
  - Heteroatoms

**Usage:**
```python
from src.utils.pdb_analyzer import analyze_pdb

result = analyze_pdb.invoke({"pdb_file": "path/to/file.pdb"})
if result["success"]:
    analysis = result["analysis"]
    print(f"Has protein: {analysis['protein']['present']}")
    print(f"Has ligand: {analysis['ligands']['present']}")
```

## Workflow Pipeline

### Step 1: User Input → Supervisor Validation
```
User Prompt: "Run MD simulation on protein.pdb with protein only"
           ↓
┌──────────────────────────────────────────────────┐
│ Supervisor: Input Validation                     │
│  1. Extract PDB path: "protein.pdb"              │
│  2. Analyze PDB:                                 │
│     - 5000 atoms, 2 protein chains              │
│     - 1 ligand (ATP)                            │
│     - Water molecules present                   │
│  3. Parse intent: "protein only" → exclude ligand│
│  4. Validate feasibility: ✓ PASSED              │
│  5. Create structured prompt                     │
└──────────────────────────────────────────────────┘
           ↓
Structured Prompt:
"MD Simulation Setup Request:
 SYSTEM: protein (2 chains)
 PREPROCESSING: add hydrogens, remove water, remove ligand
 GOAL: Run MD simulation on protein.pdb with protein only
 PDB_FILE: PDB with 5000 atoms"
```

### Step 2: Structured Prompt → Planner
```
┌──────────────────────────────────────────────────┐
│ Planner: Create Execution Plan                   │
│  - Analyze requirements from structured prompt   │
│  - Generate 3 steps:                             │
│    1. Preprocessing (remove ligand, add H)       │
│    2. Setup (topology, solvate, ions)           │
│    3. HPC Submission (run simulation)           │
│  - Define dependencies: 2 depends on 1, etc.    │
└──────────────────────────────────────────────────┘
```

### Step 3: Execution Plan → Supervisor → Field Agents
```
┌──────────────────────────────────────────────────┐
│ Supervisor: Execute Step 1                       │
│  - Route to preprocessing_agent                  │
│  - Pass: raw_pdb, component_selection, tasks     │
└──────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────┐
│ Preprocessing Agent                              │
│  - Remove ligand (ATP)                           │
│  - Add missing hydrogens                         │
│  - Remove water molecules                        │
│  - Output: cleaned_pdb                           │
└──────────────────────────────────────────────────┘
           ↓ (returns to supervisor)
┌──────────────────────────────────────────────────┐
│ Supervisor: Increment step counter (1 → 2)       │
│  - Execute Step 2                                │
│  - Route to setup_agent                          │
└──────────────────────────────────────────────────┘
           ↓
┌──────────────────────────────────────────────────┐
│ Setup Agent                                      │
│  - Generate topology (protein only)              │
│  - Add water box                                 │
│  - Add neutralizing ions                         │
│  - Output: topology, coordinates, mdp_files      │
└──────────────────────────────────────────────────┘
           ↓ (and so on...)
```

### Step 4: All Steps Complete → Final Report
```
┌──────────────────────────────────────────────────┐
│ Supervisor: All steps executed                   │
│  - Mark plan_executed = True                     │
│  - Route to final_report                         │
└──────────────────────────────────────────────────┘
```

## Key Features

### 1. **Intent-Based Component Selection**

The system recognizes user intent and adjusts processing accordingly:

| User Prompt | Interpretation | Action |
|-------------|----------------|--------|
| "protein only" | Exclude ligand, ions | Remove non-protein components |
| "without ligand" | Exclude ligand | Keep protein, remove ligand |
| "complex" or "protein-ligand" | Include both | Keep all detected components |
| "chain A" | Specific chain | Extract only chain A |

### 2. **Feasibility Validation**

Before planning, the supervisor validates:
- ✅ Requested components exist in PDB
- ✅ Specified chains are available
- ✅ File format is compatible
- ⚠️ Warns about preprocessing needs (missing H, water, etc.)

**Example Error:**
```
User: "Simulate ligand from protein.pdb"
PDB Analysis: No ligand detected
Supervisor: ERROR - "User requested ligand simulation but PDB contains no ligand"
```

### 3. **Dependency-Aware Execution**

Each step declares dependencies:
```python
Step 1: Preprocessing    dependencies: []
Step 2: Setup           dependencies: [1]  # Requires cleaned_pdb from Step 1
Step 3: HPC             dependencies: [2]  # Requires topology from Step 2
Step 4: Analysis        dependencies: [3]  # Requires trajectory from Step 3
```

Supervisor ensures steps execute in order and dependencies are satisfied.

### 4. **Structured Prompts**

Transforms natural language into structured specifications:

**Before:**
```
"I want to run MD on my protein file test.pdb"
```

**After (Structured):**
```
MD Simulation Setup Request:
SYSTEM: protein (3 chain(s)) + ligand (ADP, MG)
PREPROCESSING: add hydrogens, remove water
GOAL: Run MD simulation on test.pdb
PDB_FILE: PDB with 12453 atoms
```

## Configuration Files

### Supervisor Config
`agentic/configs/intelligent_supervisor.yaml` (or `config_supervisor.yaml`)

```yaml
supervisor:
  input_validation:
    pdb_search_patterns:
      - "(?:^|\\s)([\\w/\\-\\.]+\\.pdb)"
      - "(?:file|path)[:\\s]+([\\w/\\-\\.]+\\.pdb)"
```

### Planner Config
`agentic/planner/config.yaml`

Templates can still be used as fallback if PDB analysis is unavailable.

## Testing

Run the test suite:
```bash
python test_new_architecture.py
```

**Tests:**
1. PDB Analysis functionality
2. Supervisor input validation
3. Planner structured plan generation
4. Architecture overview

## Migration Notes

### For Existing Workflows

The enhanced architecture is **backward compatible**:
- Old workflows without PDB analysis will still function
- `rephrased_goal` is maintained for compatibility
- Planner falls back to template-based planning if no `pdb_analysis`

### Required Updates

If using the new architecture:
1. Ensure `MDAnalysis` is installed: `pip install MDAnalysis`
2. Update state initialization to include new fields
3. Field agents should return to supervisor (already implemented)

## Example Usage

```python
from agentic.workflow import MDWorkflow
from agentic.llm import LLMClient

# Initialize
llm = LLMClient(base_url="http://localhost:11434", model="llama3.2")
workflow = MDWorkflow(llm_client=llm)

# Create state with user goal
state = {
    "user_goal": "Run MD simulation on data/protein.pdb with protein only",
    "md_engine": "gromacs",
    "force_field": "amber99sb-ildn",
    "water_model": "tip3p",
    "human_in_loop": False,
    # ... other required fields
}

# Execute workflow
final_state = workflow.graph.invoke(state)

# Check results
print(f"PDB Analysis: {final_state['pdb_analysis']}")
print(f"Structured Prompt: {final_state['structured_prompt']}")
print(f"Execution Plan: {final_state['execution_plan']}")
print(f"Steps Executed: {final_state['current_step']}/{len(final_state['execution_plan']['steps'])}")
```

## Benefits

1. **Smarter Planning**: Plans adapt to actual PDB contents
2. **User Intent Recognition**: Understands "protein only", "without ligand", etc.
3. **Early Validation**: Catches infeasible requests before processing
4. **Transparent Execution**: Clear step-by-step progress tracking
5. **Dependency Safety**: Ensures steps execute in correct order
6. **Better Debugging**: Structured logs show exact component selections

## Future Enhancements

- [ ] Multi-file PDB support (complexes from separate files)
- [ ] Interactive component selection (GUI/CLI for chain/ligand picking)
- [ ] Advanced mutation/modification planning
- [ ] Automatic force field recommendation based on system composition
- [ ] Checkpoint/resume capability for long workflows

---

**Last Updated:** February 4, 2026
**Version:** 2.0
**Authors:** AgenticAI Team
