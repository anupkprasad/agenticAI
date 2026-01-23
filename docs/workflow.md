# AgenticAI Workflow - Complete Code Flow Documentation

This document describes the complete execution flow of the AgenticAI system from user entry point to final output.

## 📋 Table of Contents

1. [Entry Point](#entry-point)
2. [Workflow Initialization](#workflow-initialization)
3. [State Management](#state-management)
4. [Execution Pipeline](#execution-pipeline)
5. [Agent Execution Details](#agent-execution-details)
6. [Decision Making & Routing](#decision-making--routing)
7. [Logging & Transparency](#logging--transparency)
8. [Output & Completion](#output--completion)

---

## Entry Point

### User CLI Invocation

```bash
python run_agenticAIWork.py \
  --goal "Prepare MD simulation for ATP.pdb with AMBER force field" \
  --use-llm \
  --llm-model gpt-oss:20b \
  --llm-base-url http://127.0.0.1:11434 \
  --working-dir ./working_dir/ATP.pdb/ \
  --no-human-loop
```

**File:** `run_agenticAIWork.py` (Lines 1-163)

### Entry Point Flow

```
run_agenticAIWork.py (main)
    ↓
Parse command-line arguments (argparse)
    ↓
Initialize LLMClient with user-provided credentials
    ↓
Create MDWorkflow instance with LLMClient
    ↓
Call workflow.run() with user goal and config
```

### Key Parameters Captured

- `--goal`: Natural language description of the task
- `--use-llm`: Enable LLM routing (vs. fallback heuristic mode)
- `--llm-model`: Model name (default: `gpt-oss:20b`)
- `--llm-base-url`: LLM server endpoint (default: `http://127.0.0.1:11434`)
- `--working-dir`: Output directory for generated files
- `--no-human-loop`: Skip human approval checkpoints
- `--force-field`: MD force field (default: `amber99sb-ildn`)
- `--water-model`: Water model (default: `tip3p`)

---

## Workflow Initialization

### MDWorkflow Class Initialization

**File:** `agentic/workflow.py` (Lines 18-45)

```python
def __init__(self, llm_client: Optional[LLMClient] = None):
    self.llm = llm_client  # LLM for intelligent routing
    self.supervisor = MDSupervisor(llm_client=llm_client)
    self.preprocess_agent = PreprocessingAgent(llm_client=llm_client)
    self.setup_agent = SimulationSetupAgent(llm_client=llm_client)
    self._build_graph()  # Construct LangGraph StateGraph
```

### LangGraph State Graph Construction

**File:** `agentic/workflow.py` (Lines 47-150)

The workflow builds a directed acyclic graph (DAG) with these nodes:

```
Graph Structure:
├── input_validation (START)
│   └── Input analysis & PDB extraction
├── supervisor
│   └── LLM-powered routing decision
├── preprocessing
│   └── PDB cleaning & protonation
├── setup
│   └── System solvation & MDP generation
├── hpc (stub)
│   └── Job submission & execution
├── analysis (stub)
│   └── Trajectory analysis
├── human_preprocess_check (conditional)
├── human_setup_check (conditional)
└── final_report (END)
    └── Comprehensive summary
```

### Graph Connectivity

Edges (conditional routing based on `next_node` field):

```
input_validation → supervisor
supervisor → preprocessing | setup | hpc | analysis | final_report
preprocessing → supervisor (loops back for next decision)
setup → supervisor
... (feedback loops as needed)
any_node → final_report (terminal node)
```

---

## _build_graph Function Deep Dive

The `_build_graph()` function is the core of the MDWorkflow initialization. It constructs the LangGraph StateGraph that orchestrates the entire MD simulation workflow.

**File:** `agentic/workflow.py` (Lines 45-120)

### Function Overview

```python
def _build_graph(self) -> StateGraph:
    """Build the LangGraph workflow."""
```

**Purpose:** Construct a directed graph representation of the MD workflow with all nodes, edges, and conditional routing logic.

**Returns:** A compiled LangGraph StateGraph ready for execution

### Step-by-Step Breakdown

#### Step 1: Create StateGraph Instance

```python
workflow = StateGraph(MDState)
```

- Creates a new LangGraph StateGraph with MDState as the state schema
- MDState is a TypedDict that defines all fields flowing through the workflow
- The graph uses this schema to validate state updates at each node

#### Step 2: Add All Workflow Nodes

```python
workflow.add_node("supervisor", self.supervisor.supervisor_node)
workflow.add_node("input_validation", self.supervisor.input_validation_node)
workflow.add_node("preprocess", self.preprocessor.preprocess_node)
workflow.add_node("setup", self.setup_agent.setup_node)
workflow.add_node("human_preprocess_check", self.checkpoints.human_preprocess_check)
workflow.add_node("human_setup_check", self.checkpoints.human_setup_check)
workflow.add_node("final_report", self._final_report_node)
```

**Node Registration Details:**

| Node Name | Handler Function | Purpose | Type |
|-----------|-----------------|---------|------|
| `supervisor` | `supervisor.supervisor_node()` | LLM-based routing decisions | Decision Node |
| `input_validation` | `supervisor.input_validation_node()` | Parse user goal, extract PDB path | Processing Node |
| `preprocess` | `preprocessor.preprocess_node()` | Clean PDB, add hydrogens | Processing Node |
| `setup` | `setup_agent.setup_node()` | Solvate, generate MDP files | Processing Node |
| `human_preprocess_check` | `checkpoints.human_preprocess_check()` | Optional human approval | Checkpoint Node |
| `human_setup_check` | `checkpoints.human_setup_check()` | Optional human approval | Checkpoint Node |
| `final_report` | `_final_report_node()` | Generate completion report | Terminal Node |

Each `add_node()` call registers:
- **Node name** (string): Unique identifier used in routing
- **Handler function** (callable): Method that processes the state and returns updated state

#### Step 3: Set Entry Point

```python
workflow.set_entry_point("supervisor")
```

- Designates "supervisor" as the starting node
- When `graph.invoke()` is called, execution begins at this node
- Note: While supervisor is the entry point, it may route to `input_validation` first if raw_pdb is not set

#### Step 4: Add Conditional Edges

Conditional edges use routing functions to decide the next node based on state:

##### From Supervisor (Primary Router)

```python
workflow.add_conditional_edges(
    "supervisor",
    self._route_from_supervisor,
    {
        "input_validation": "input_validation",
        "preprocess": "preprocess", 
        "setup": "setup",
        "final_report": "final_report",
        END: END
    }
)
```

**Components:**
- **Source node:** "supervisor" - where routing decision happens
- **Router function:** `_route_from_supervisor(state)` - examines state and returns next node name
- **Routing map:** Dictionary mapping router return values to actual node names
- **Fallback:** END terminates workflow if no matching route

**Router Function Logic:**

```python
def _route_from_supervisor(self, state: MDState) -> str:
    """Route from supervisor based on next_node."""
    next_node = state.get("next_node")
    
    # Handle special cases (not yet implemented)
    if next_node == "hpc":
        return "final_report"  # Skip to end (HPC not implemented)
    elif next_node == "analysis":
        return "final_report"  # Skip to end (analysis not implemented)
    elif next_node is None:
        return END  # Terminate
    else:
        return next_node  # Route to specified node
```

The supervisor sets `state["next_node"]` to indicate where to go next. This router:
1. Extracts that value from state
2. Applies any transformations (e.g., skip unimplemented nodes)
3. Returns the target node name

##### From Input Validation

```python
workflow.add_conditional_edges(
    "input_validation",
    lambda state: state["next_node"],
    {"supervisor": "supervisor"}
)
```

- Simple routing: input_validation always returns to supervisor
- Uses a lambda to extract `next_node` from state
- Routes to supervisor for decision on next step

##### From Preprocessing Agent

```python
workflow.add_conditional_edges(
    "preprocess",
    lambda state: state["next_node"],
    {
        "supervisor": "supervisor",
        "human_preprocess_check": "human_preprocess_check"
    }
)
```

- Preprocessing can route to:
  - **supervisor**: Continue normal workflow (no human approval needed)
  - **human_preprocess_check**: Pause for human review (if `human_in_loop=True`)

##### From Setup Agent

```python
workflow.add_conditional_edges(
    "setup", 
    lambda state: state["next_node"],
    {
        "supervisor": "supervisor",
        "human_setup_check": "human_setup_check"
    }
)
```

- Similar to preprocessing: can skip human check or route to it

##### From Human Checkpoints

```python
workflow.add_conditional_edges(
    "human_preprocess_check",
    lambda state: state["next_node"],
    {
        "supervisor": "supervisor",
        "preprocess": "preprocess",        # Re-run preprocessing
        "human_preprocess_check": "human_preprocess_check"  # Stay in checkpoint
    }
)

workflow.add_conditional_edges(
    "human_setup_check",
    lambda state: state["next_node"], 
    {
        "supervisor": "supervisor",       # Approve and continue
        "setup": "setup",                 # Re-run setup
        "human_setup_check": "human_setup_check"  # Stay in checkpoint
    }
)
```

Human checkpoint loops allow:
1. **Approve & Continue** (`→ supervisor`): Accept current results, move forward
2. **Redo Step** (`→ preprocess/setup`): Re-run with modifications
3. **Stay in Checkpoint** (self-loop): Keep discussing/revising

#### Step 5: Terminal Edge

```python
workflow.add_edge("final_report", END)
```

- Simple edge (not conditional): final_report always terminates the workflow
- END is a special LangGraph constant indicating workflow completion
- No further processing after final_report

#### Step 6: Compile and Return

```python
return workflow.compile()
```

- Compiles the graph into an executable form
- Validates graph structure (cycles, missing edges, etc.)
- Returns compiled graph ready for `.invoke()` calls
- Compilation happens once during __init__, not per execution

### Graph Topology Visualization

```
                    ┌──────────────┐
                    │   START      │
                    │ (supervisor) │
                    └──────┬───────┘
                           │
                ┌──────────▼──────────┐
                │ _route_from_        │
                │ supervisor()        │
                └──────────┬──────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
        ▼                  ▼                  ▼
    ┌────────────┐  ┌───────────┐  ┌────────────┐
    │   input_   │  │ preprocess│  │   setup    │
    │ validation │  │           │  │            │
    └─────┬──────┘  └─┬───┬─────┘  └─┬────┬────┘
          │           │   │          │    │
    ┌─────▼─────┐  ┌──┴───┴──┐  ┌───┴────┴──┐
    │supervisor │  │supervisor│  │supervisor │
    │  routing  │  │ routing  │  │ routing   │
    └───┬───┬───┘  └─┬──────┬─┘  └─┬──────┬──┘
        │   │        │      │      │      │
        │   └────────┤      │      │      │
        │            │      │      │      │
        └─┐  ┌──────────────┤  ┌───┘  ┌────────┐
          │  │              │  │      │        │
          ▼  ▼              ▼  ▼      ▼        ▼
      ┌──────────────┐  ┌──────────┐  ┌──────────────┐
      │  human_     │  │          │  │   final_     │
      │  check_pre  │  │supervisor│  │   report     │
      └──────┬──────┘  └─────┬────┘  └──────┬───────┘
             │                │             │
             └────────────────┴─────────────┘
                              │
                          ┌───▼────┐
                          │  END    │
                          └─────────┘
```

### State Mutation Pattern

Each node follows this pattern:

```python
def node_handler(state: MDState) -> MDState:
    # 1. Process inputs from state
    input_data = state.get("input_field")
    
    # 2. Perform computation
    result = process(input_data)
    
    # 3. Update state
    state["output_field"] = result
    
    # 4. Set next routing decision
    state["next_node"] = determine_next_node(state)
    
    # 5. Return updated state
    return state
```

Key points:
- State is passed in and modified in-place
- Return the updated state
- Must set `state["next_node"]` to control routing
- Each node contributes its results to the accumulating state

### Execution Flow Through Graph

```
invoke(initial_state)
    │
    └─► Supervisor node
        │ (routes based on state["next_node"])
        │
        ├─► Input Validation (if raw_pdb missing)
        │   └─► Supervisor (loops back)
        │
        ├─► Preprocessing (if cleaned_pdb missing)
        │   ├─► Human Check (if human_in_loop=True and issues found)
        │   │   └─► Supervisor (loops back)
        │   └─► Supervisor (loops back)
        │
        ├─► Setup (if coordinates missing)
        │   ├─► Human Check (if human_in_loop=True)
        │   │   └─► Supervisor (loops back)
        │   └─► Supervisor (loops back)
        │
        └─► Final Report
            └─► END (workflow complete)
```

### Graph Recursion Protection

The workflow uses LangGraph's recursion limit to prevent infinite loops:

```python
final_state = compiled_graph.invoke(
    initial_state,
    config={"recursion_limit": 25}  # Max 25 iterations
)
```

This prevents:
- Infinite loops from routing errors
- Runaway supervisors
- Circular dependency hangs

If 25 iterations are exceeded, the workflow terminates with an error.

### Key Design Decisions

1. **Supervisor as Entry Point**: Always start with routing decision (can skip directly to input_validation if needed)

2. **Conditional Edges Over Simple Edges**: Use routing functions for flexibility and clear decision logic

3. **Human Checkpoints Optional**: Graph includes human approval nodes but they're only visited if `human_in_loop=True`

4. **Feedback Loops**: Agents can loop back to supervisor for re-routing, not directly to next step

5. **Terminal Node Explicit**: Final report is explicit node, not just an end condition

6. **State-Driven Routing**: All routing decisions based on state fields, making the flow transparent and testable

---

## State Management

### MDState TypedDict Definition

**File:** `agentic/state.py`

The central state object flows through the entire workflow with these key fields:

#### Input & Configuration
```python
{
    "user_goal": str,                    # Original user request
    "force_field": str,                  # "amber99sb-ildn" (default)
    "water_model": str,                  # "tip3p" (default)
    "working_directory": str,            # Output directory path
    "human_in_loop": bool,               # Enable checkpoints
}
```

#### Extracted Information
```python
{
    "raw_pdb": str,                      # Path to input PDB file
    "pdb_content_analysis": dict,        # Structure analysis results
    "user_intent_analysis": str,         # LLM interpretation of goal
    "data_stage": str,                   # "raw_pdb" | "preprocessed" | "setup_complete" | "simulation_complete"
}
```

#### Preprocessing Results
```python
{
    "cleaned_pdb": str,                  # Path to preprocessed structure
    "preprocessing_plan": str,           # LLM-generated preprocessing steps
    "preprocessing_report": str,         # Execution results
    "preprocessing_issues": list,        # Validation errors/warnings
}
```

#### Setup Results
```python
{
    "coordinates": str,                  # Solvated .gro file path
    "topology": str,                     # GROMACS topology (.top)
    "setup_plan": str,                   # Setup strategy from LLM
    "setup_report": str,                 # Generated parameters report
    "mdp_files": dict,                   # {"minim": path, "nvt": path, ...}
}
```

#### HPC & Analysis
```python
{
    "job_id": str,                       # HPC job identifier
    "analysis_results": dict,            # RMSD, trajectory info, etc.
}
```

#### Execution Tracking
```python
{
    "next_node": str,                    # Next routing destination
    "errors": list[str],                 # Accumulated errors
    "warnings": list[str],               # Accumulated warnings
    "session_id": str,                   # Unique session identifier
}
```

### State Flow Through Pipeline

```
Initial State (from CLI args)
    ↓
input_validation_node() → adds raw_pdb, pdb_content_analysis
    ↓
supervisor_node() → decides next_node
    ↓
[preprocessing_node() | setup_node() | ...]
    → each agent adds its outputs to state
    ↓
supervisor_node() → decides next_node (may loop back)
    ↓
final_report_node() → generates summary from entire state
    ↓
Return state with all accumulated results
```

---

## Execution Pipeline

### Sequential Node Execution in LangGraph

**File:** `agentic/workflow.py` (Lines 152-200)

The graph is invoked using LangGraph's synchronous executor:

```python
def run(self, user_goal: str, config: Optional[Dict[str, Any]] = None):
    # 1. Initialize state with user inputs
    initial_state = MDState(
        user_goal=user_goal,
        force_field=config.get("force_field", "amber99sb-ildn"),
        water_model=config.get("water_model", "tip3p"),
        working_directory=config.get("working_directory", "."),
        human_in_loop=config.get("human_in_loop", True),
        errors=[],
        warnings=[],
        session_id=self._generate_session_id(),
    )
    
    # 2. Compile and execute the graph
    compiled_graph = self.graph.compile()
    final_state = compiled_graph.invoke(
        initial_state,
        config={"recursion_limit": 25}  # Prevent infinite loops
    )
    
    # 3. Return results
    return final_state
```

### Graph Compilation & Execution

```
User Goal Input
    ↓
MDState(user_goal=..., working_directory=..., ...)
    ↓
StateGraph.compile()
    ↓
Graph execution starts at START node (input_validation)
    ↓
Each node processes state and returns updated state
    ↓
Router logic selects next node based on state["next_node"]
    ↓
Repeat until END node (final_report) reached
    ↓
Return complete final_state
```

---

## Agent Execution Details

### 1. Input Validation Node

**File:** `agentic/supervisor.py` (Lines 350-410)

**Purpose:** Extract structured information from user goal

**Execution:**

```python
def input_validation_node(state: MDState) -> MDState:
    # Step 1: Use LLM to analyze user goal (if enabled)
    if self.llm:
        validation_result = self._llm_input_analysis(user_goal)
        # Prompt LLM to extract:
        # - PDB_PATH: file location
        # - WORKING_DIR: output directory
        # - FORCE_FIELD: simulation force field
        # - WATER_MODEL: solvent model
        # - DATA_STAGE: current processing stage
        # - USER_INTENT: what user is trying to achieve
        
        extracted_info = self._parse_input_analysis(validation_result)
        # Maps LLM output to state keys:
        # PDB_PATH → raw_pdb
        # WORKING_DIR → working_directory
        # FORCE_FIELD → force_field
        # WATER_MODEL → water_model
        # DATA_STAGE → data_stage
        # USER_INTENT → user_intent_analysis
    else:
        # Fallback: Regex extraction of .pdb path
        pdb_path = self._extract_pdb_path(user_goal)
        state["raw_pdb"] = pdb_path
    
    state["next_node"] = "supervisor"  # Route to supervisor
    return state
```

**Inputs:**
- `state.user_goal` - Natural language description
- `state.working_directory` - From CLI args

**Outputs:**
- `state.raw_pdb` - Path to PDB file
- `state.pdb_content_analysis` - File analysis
- `state.working_directory` - Confirmed output path
- `state.force_field`, `state.water_model` - Extracted params
- `state.user_intent_analysis` - LLM interpretation

**Logging:**
```
✅ INPUT_VALIDATION extracted:
   PDB_PATH: ATP.pdb
   WORKING_DIR: ./working_dir/ATP.pdb/
   FORCE_FIELD: amber99sb-ildn (default)
   DATA_STAGE: raw_pdb
   USER_INTENT: Prepare MD simulation for ATP.pdb
```

---

### 2. Supervisor Routing Node

**File:** `agentic/supervisor.py` (Lines 95-180)

**Purpose:** Intelligent routing to appropriate agent

**Execution:**

```python
def supervisor_node(state: MDState) -> MDState:
    # Step 1: Check prerequisites
    if not state.get("raw_pdb"):
        next_agent = "input_validation"
        
    # Step 2: Use LLM to analyze current state and decide
    elif self.llm:
        routing_prompt = f"""
        Analyze workflow state and determine next step:
        - raw_pdb: {state.get('raw_pdb')}
        - cleaned_pdb: {state.get('cleaned_pdb')}
        - coordinates: {state.get('coordinates')}
        - user_goal: {state.get('user_goal')}
        
        What is the next required step?
        Options: preprocessing | setup | hpc | analysis | final_report
        """
        
        routing_result = self.llm.generate(routing_prompt)
        # LLM response format:
        # NEXT_AGENT: preprocessing
        # REASONING: Raw PDB needs cleaning before setup
        
        next_agent = self._parse_routing_decision(routing_result)
        
    else:
        # Fallback heuristic routing
        if not state.get("cleaned_pdb"):
            next_agent = "preprocessing"
        elif not state.get("coordinates"):
            next_agent = "setup"
        else:
            next_agent = "final_report"
    
    state["next_node"] = next_agent
    log_supervisor_routing(state, next_agent, reasoning)
    return state
```

**Decision Logic:**

```
If raw_pdb not set:
    → input_validation (extract PDB path)
Else if cleaned_pdb not set:
    → preprocessing (clean PDB, add hydrogens)
Else if coordinates not set:
    → setup (solvate, generate parameters)
Else if not human_in_loop:
    → final_report (summarize)
Else:
    → human approval checkpoints
```

**Logging:**
```
🧠 LLM SUPERVISOR ROUTING:
   Input: raw_pdb=ATP.pdb, cleaned_pdb=None
   Decision: preprocessing
   Reasoning: Raw PDB needs cleaning and protonation
```

---

### 3. Preprocessing Agent Node

**File:** `agentic/preprocess/preprocessing_agent.py` (Lines 24-73)

**Purpose:** Clean PDB, add hydrogens, prepare for GROMACS

**Execution:**

```python
def preprocess_node(state: MDState) -> MDState:
    log_agent_start("preprocessing", "PDB Cleaning", state)
    
    try:
        # 1. Analyze PDB structure
        pdb_path = state.get("raw_pdb")
        analysis = self._analyze_pdb_structure(state)
        # Returns: {
        #   "file_exists": bool,
        #   "has_heteroatoms": bool,
        #   "chain_count": int,
        #   "waters_present": bool,
        #   "missing_residues": list
        # }
        
        # 2. Generate preprocessing plan (LLM)
        if self.llm:
            plan = self._generate_preprocessing_plan(state, analysis)
            # LLM generates step-by-step cleaning commands
        else:
            plan = self._default_preprocessing_plan(analysis)
        
        # 3. Execute preprocessing
        result = self._execute_preprocessing(plan)
        # Returns: {
        #   "cleaned_pdb": "./working_dir/ATP.pdb/processed.gro",
        #   "topology": "./working_dir/ATP.pdb/topol.top",
        #   "execution_log": "command output"
        # }
        
        # 4. Update state
        state.update(result)
        state["data_stage"] = "preprocessed"
        state["next_node"] = "supervisor"  # Loop back for routing
        
        log_agent_completion("preprocessing", "PDB Cleaning", state, success=True)
        
    except Exception as e:
        logger.error(f"Preprocessing failed: {e}")
        from ..utils import log_error
        log_error("preprocessing_agent.preprocess_node", e, {"state": state})
        state["errors"].append(f"Preprocessing error: {str(e)}")
        state["next_node"] = "supervisor"
    
    return state
```

**Key Operations:**

```
Input: state with raw_pdb (e.g., "ATP.pdb")

1. Analyze PDB:
   ✓ Check if file exists
   ✓ Count atoms, residues, chains
   ✓ Detect heteroatoms, waters
   
2. Generate Plan (LLM analyzes):
   ✓ Add missing chain IDs if needed
   ✓ Add missing hydrogens
   ✓ Assign charges (AMBER99SB-ILDN)
   ✓ Remove/keep waters
   
3. Execute Commands:
   gmx pdb2gmx -f ATP.pdb -o processed.gro -p topol.top
   gmx editconf -f processed.gro -o system.gro -d 1.0
   
4. Output Files:
   - processed.gro (cleaned coordinates)
   - topol.top (GROMACS topology)
   - execution_log (commands run)
```

**Logging:**
```
🏁 PREPROCESSING AGENT ✅ COMPLETED:
   Input: raw_pdb=ATP.pdb
   Output: cleaned_pdb=processed.gro, topology=topol.top
   Status: Ready for setup
```

---

### 4. Setup Agent Node

**File:** `agentic/simsetup/setup_agent.py` (Lines 24-75)

**Purpose:** Solvate system, generate MDP files for MD simulation

**Execution:**

```python
def setup_node(state: MDState) -> MDState:
    log_agent_start("setup", "System Setup", state)
    
    try:
        # 1. Analyze preprocessed system
        analysis = self._analyze_system(state)
        # Returns: {
        #   "num_atoms": int,
        #   "num_residues": int,
        #   "total_charge": float
        # }
        
        # 2. Generate setup plan (LLM)
        if self.llm:
            plan = self._generate_setup_plan(state, analysis)
            # LLM generates:
            # - Box size and type (cubic, triclinic)
            # - Solvation strategy (solvent type, padding)
            # - Ion neutralization (counterions for charge)
            # - MDP parameters (time step, temperature, etc.)
        else:
            plan = self._default_setup_plan()
        
        # 3. Execute setup
        result = self._execute_setup(plan)
        # Returns: {
        #   "coordinates": "./working_dir/ATP.pdb/system.gro",
        #   "mdp_files": {
        #       "minim": "minim.mdp",
        #       "nvt": "nvt.mdp",
        #       "npt": "npt.mdp",
        #       "md": "md.mdp"
        #   },
        #   "execution_log": "..."
        # }
        
        # 4. Update state
        state.update(result)
        state["data_stage"] = "setup_complete"
        state["next_node"] = "supervisor"
        
        log_agent_completion("setup", "System Setup", state, success=True)
        
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        from ..utils import log_error
        log_error("setup_agent.setup_node", e, {"state": state})
        state["errors"].append(f"Setup error: {str(e)}")
        state["next_node"] = "supervisor"
    
    return state
```

**Key Operations:**

```
Input: state with cleaned_pdb

1. Analyze System:
   ✓ Count atoms/residues
   ✓ Calculate net charge
   ✓ Estimate system size
   
2. Generate MDP Files:
   - minim.mdp: Energy minimization (1000 steps)
   - nvt.mdp: NVT equilibration (100 ps, 300K)
   - npt.mdp: NPT equilibration (100 ps, 1 atm)
   - md.mdp: Production MD (parameters user-configurable)
   
3. Generate Coordinates:
   gmx editconf -f cleaned.gro -o boxed.gro -d 1.0 -bt cubic
   gmx solvate -cp boxed.gro -cs spc216.gro -o solv.gro
   gmx genion -s system.tpr -o ions.gro (neutralize charge)
   
4. Output Files:
   - system.gro (solvated coordinates)
   - topol.top (updated topology with ions)
   - *.mdp (4 MDP parameter files)
```

**Logging:**
```
🏁 SETUP AGENT ✅ COMPLETED:
   Input: cleaned_pdb=processed.gro
   Generated: 4 MDP files, solvated system
   System: 12,345 atoms in cubic box
   Status: Ready for simulation
```

---

### 5. HPC Agent Node (Stub)

**File:** `agentic/hpc/__init__.py`

**Purpose:** Submit jobs to HPC cluster, monitor execution

**Current Status:** Placeholder for future implementation

```python
def hpc_node(state: MDState) -> MDState:
    # TODO: Implement HPC job submission
    # Would use Paramiko/SSH to submit SLURM jobs
    # Track job_id and monitor completion
    state["next_node"] = "final_report"
    return state
```

---

### 6. Analysis Agent Node (Stub)

**File:** `agentic/analysis/__init__.py`

**Purpose:** Analyze trajectories, generate reports

**Current Status:** Placeholder for future implementation

```python
def analysis_node(state: MDState) -> MDState:
    # TODO: Implement trajectory analysis
    # Would use MDAnalysis to compute:
    # - RMSD, RMSF
    # - Radius of gyration
    # - Hydrogen bonds
    # - Secondary structure evolution
    state["next_node"] = "final_report"
    return state
```

---

### 7. Final Report Node

**File:** `agentic/workflow.py` (Lines 220-250)

**Purpose:** Generate comprehensive workflow summary

**Execution:**

```python
def final_report_node(state: MDState) -> MDState:
    report = f"""
    ╔════════════════════════════════════════════════════════╗
    ║          WORKFLOW COMPLETION SUMMARY                   ║
    ╚════════════════════════════════════════════════════════╝
    
    Session ID: {state["session_id"]}
    Status: {'✅ SUCCESS' if not state["errors"] else '❌ FAILED'}
    
    Input & Configuration:
    - User Goal: {state["user_goal"]}
    - Force Field: {state["force_field"]}
    - Water Model: {state["water_model"]}
    - Working Directory: {state["working_directory"]}
    
    Generated Files:
    - Preprocessed PDB: {state.get("cleaned_pdb", "N/A")}
    - Topology: {state.get("topology", "N/A")}
    - Solvated Coordinates: {state.get("coordinates", "N/A")}
    - MDP Files: {len(state.get("mdp_files", {}))} generated
    
    Errors ({len(state["errors"])}):
    {chr(10).join(f"  - {e}" for e in state["errors"])}
    
    Warnings ({len(state["warnings"])}):
    {chr(10).join(f"  - {w}" for w in state["warnings"])}
    
    Total Execution Time: {datetime.now() - start_time}
    """
    
    print(report)
    # Save to log file
    save_workflow_summary(state, report)
    
    return state
```

**Output Locations:**
- Console: Human-readable summary
- File: `agent_conversation.log` - Complete execution log
- Working directory: Generated simulation files

---

## Decision Making & Routing

### LLM-Powered Routing Flow

```
User Input
    ↓
Input Validation extracts PDB path
    ↓
Supervisor analyzes state with LLM:
    "What is the next required step?"
    ↓
    LLM considers current state:
    - Has raw PDB? ✓
    - Has cleaned PDB? ✗
    - Has coordinates? ✗
    ↓
    LLM decides: preprocessing
    ↓
Preprocessing Agent executes
    ↓
Agent returns updated state with cleaned_pdb
    ↓
Supervisor analyzes state again:
    "What is the next required step?"
    ↓
    LLM considers current state:
    - Has raw PDB? ✓
    - Has cleaned PDB? ✓
    - Has coordinates? ✗
    ↓
    LLM decides: setup
    ↓
Setup Agent executes
    ... (loop continues)
    ↓
Until final_report is reached
```

### Heuristic Fallback Routing

When LLM is unavailable, use simple rule-based routing:

```python
if not state.get("raw_pdb"):
    next_node = "input_validation"
elif not state.get("cleaned_pdb"):
    next_node = "preprocessing"
elif not state.get("coordinates"):
    next_node = "setup"
elif not state.get("job_id"):
    next_node = "hpc"
elif not state.get("analysis_results"):
    next_node = "analysis"
else:
    next_node = "final_report"
```

---

## Logging & Transparency

### Conversation Logger

**File:** `agentic/utils/conversation_logger.py`

All workflow interactions are logged to `agent_conversation.log`:

```
LOG STRUCTURE:

🎯 SESSION START [2026-01-23 15:10:25]:
   Goal: "Prepare MD simulation for ATP.pdb"
   Configuration: force_field=amber99sb-ildn, working_dir=...

📝 INPUT VALIDATION [15:10:30]:
   ✅ Extracted: PDB_PATH=ATP.pdb, WORKING_DIR=./working_dir/ATP.pdb/

🧠 LLM ROUTING [15:10:35]:
   Query: What is next step?
   Decision: preprocessing
   Reasoning: Raw PDB needs cleaning

⚡ PREPROCESSING [15:10:40]:
   Command: gmx pdb2gmx -f ATP.pdb ...
   Output: processed.gro (72 bytes)
   Status: ✅ SUCCESS

🧠 LLM ROUTING [15:11:45]:
   Query: What is next step?
   Decision: setup
   Reasoning: Cleaned PDB needs solvation

⚡ SETUP [15:12:00]:
   Generated: 4 MDP files
   Solvation: TIP3P water + neutralizing ions
   Status: ✅ SUCCESS

🏁 WORKFLOW COMPLETE [15:12:30]:
   Status: ✅ SUCCESS
   Files: 7 generated
   Errors: 0
   Warnings: 0
```

### Log Functions

```python
# Log different event types
log_agent_start(stage, name, state)
log_llm_interaction(stage, prompt, response)
log_agent_action(stage, action, details)
log_file_operation(stage, operation, filepath, status)
log_agent_completion(stage, name, state, success)
log_error(location, exception, context)
```

---

## Output & Completion

### Generated Files

In working directory:

```
./working_dir/ATP.pdb/
├── processed.gro          # Cleaned, protonated structure
├── topol.top              # GROMACS topology
├── system.gro             # Solvated coordinates
├── minim.mdp              # Energy minimization parameters
├── nvt.mdp                # NVT equilibration parameters
├── npt.mdp                # NPT equilibration parameters
└── md.mdp                 # Production MD parameters
```

### State Return Value

The final state contains:

```python
{
    "user_goal": "Prepare MD simulation for ATP.pdb with AMBER force field",
    "raw_pdb": "ATP.pdb",
    "cleaned_pdb": "./working_dir/ATP.pdb/processed.gro",
    "topology": "./working_dir/ATP.pdb/topol.top",
    "coordinates": "./working_dir/ATP.pdb/system.gro",
    "mdp_files": {
        "minim": "./working_dir/ATP.pdb/minim.mdp",
        "nvt": "./working_dir/ATP.pdb/nvt.mdp",
        "npt": "./working_dir/ATP.pdb/npt.mdp",
        "md": "./working_dir/ATP.pdb/md.mdp"
    },
    "data_stage": "setup_complete",
    "force_field": "amber99sb-ildn",
    "water_model": "tip3p",
    "working_directory": "./working_dir/ATP.pdb/",
    "session_id": "20260123_151030",
    "errors": [],
    "warnings": [],
    "next_node": "final_report"
}
```

### Exit Codes

```
Exit 0: Workflow completed successfully
Exit 1: Workflow failed with errors
Exit 2: Invalid arguments or configuration
```

---

## Complete Execution Timeline Example

```
[15:10:25] START: run_agenticAIWork.py
[15:10:26] INIT: LLMClient(model=gpt-oss:20b, url=http://127.0.0.1:11434)
[15:10:27] INIT: MDWorkflow(llm_client=...)
[15:10:28] INIT: StateGraph with 8 nodes compiled

[15:10:30] NODE: input_validation
  INPUT:  goal="Prepare MD simulation for ATP.pdb"
  LLM:    "PDB_PATH: ATP.pdb, WORKING_DIR: ./working_dir/ATP.pdb/"
  OUTPUT: raw_pdb="ATP.pdb"
  NEXT:   supervisor

[15:10:35] NODE: supervisor
  ANALYZE: raw_pdb exists, cleaned_pdb missing
  LLM:    "Preprocessing needed for cleaning and protonation"
  DECISION: preprocessing
  NEXT:   preprocessing

[15:10:40] NODE: preprocessing
  ANALYZE: ATP.pdb - 100 atoms, no heteroatoms, no chain IDs
  PLAN:   Add chain IDs, run pdb2gmx, generate topology
  EXECUTE: gmx pdb2gmx -f ATP.pdb -o processed.gro -p topol.top
  OUTPUT: cleaned_pdb="processed.gro", topology="topol.top"
  NEXT:   supervisor

[15:11:45] NODE: supervisor
  ANALYZE: raw_pdb exists, cleaned_pdb exists, coordinates missing
  LLM:    "System setup needed for solvation"
  DECISION: setup
  NEXT:   setup

[15:12:00] NODE: setup
  ANALYZE: 100 atoms, neutral charge
  PLAN:   Create cubic box, add TIP3P water, neutralize
  EXECUTE: gmx editconf, gmx solvate, gmx genion
           Create minim.mdp, nvt.mdp, npt.mdp, md.mdp
  OUTPUT: coordinates="system.gro", mdp_files={...}
  NEXT:   supervisor

[15:12:30] NODE: supervisor
  ANALYZE: All prerequisites complete
  DECISION: final_report
  NEXT:   final_report

[15:12:35] NODE: final_report
  SUMMARY: 7 files generated, 0 errors
  LOG:    Saving to agent_conversation.log
  STATUS: ✅ SUCCESS

[15:12:36] EXIT: Code 0 (Success)
```

---

## Architecture Summary

```
┌──────────────────────────────────────┐
│     CLI Entry (run_agenticAIWork.py) │
└─────────────┬──────────────────────┘
              │
              ▼
    ┌─────────────────────┐
    │  LLMClient          │
    │  (Ollama HTTP)      │
    └─────────────────────┘
              │
              ▼
    ┌─────────────────────────────┐
    │  MDWorkflow                 │
    │  ├─ supervisor              │
    │  ├─ preprocess_agent        │
    │  ├─ setup_agent             │
    │  └─ StateGraph (LangGraph)  │
    └──────────┬──────────────────┘
               │
        ┌──────▼──────┐
        │ MDState      │  (Central State Container)
        │ (TypedDict)  │
        └──────────────┘
               │
        ┌──────▼────────────────┐
        │  Node Execution Loop  │
        │  ├─ input_validation  │
        │  ├─ supervisor (LLM)  │
        │  ├─ agents            │
        │  └─ final_report      │
        └──────┬────────────────┘
               │
        ┌──────▼────────────┐
        │ Output Files       │
        │ └─ working_dir/   │
        │    ├─ *.gro       │
        │    ├─ *.top       │
        │    └─ *.mdp       │
        └────────────────────┘
```

---

## Key Design Principles

1. **State-Centric**: All data flows through MDState TypedDict
2. **LLM-Powered Routing**: Intelligent decisions with fallback heuristics
3. **Modular Agents**: Independent agents for each task
4. **Transparent Logging**: Complete audit trail in agent_conversation.log
5. **Human-in-Loop Ready**: Optional checkpoints for approval
6. **Graceful Degradation**: Works with or without LLM
7. **Extensible**: Easy to add new agents or nodes to graph

