# Subtask-Specific Workflow Architecture Diagram

## High-Level System Flow

```
                          USER GOAL (Natural Language)
                                   |
                                   v
                    ┌──────────────────────────┐
                    |   SUPERVISOR: Detect     |
                    |   Subtask Type           |
                    └──────────────────────────┘
                                   |
           ┌───────────────────────┼───────────────────────┐
           |                       |                       |
    "analysis_only"        "setup_only"         "preprocess_only"
    + exclusions           + HPC exclusion           (else)
           |                       |                       |
           v                       v                       v
    ┌─────────────┐        ┌──────────────┐        ┌─────────────┐
    | SKIP PDB    |        | DO PDB       |        | DO PDB      |
    | Validation  |        | Validation   |        | Validation  |
    └─────────────┘        └──────────────┘        └─────────────┘
           |                       |                       |
           v                       v                       v
    ┌─────────────┐        ┌──────────────┐        ┌─────────────┐
    | VALIDATE    |        | PLAS ROUTES  |        | PLAN ROUTES |
    | TRAJ PATHS  |        | TO PLANNING  |        | TO PLANNING |
    └─────────────┘        └──────────────┘        └─────────────┘
           |                       |                       |
           └───────────────────────┼───────────────────────┘
                                   |
                                   v
                    ┌──────────────────────────┐
                    |   PLANNER: Generate     |
                    |   Execution Plan        |
                    |   (Subtask-Aware)       |
                    └──────────────────────────┘
                                   |
           ┌───────────────────────┼───────────────────────┐
           |                       |                       |
    ANALYSIS AGENT        PREPROCESS + SETUP      PREPROCESS AGENT
       only                   (skip HPC)              only
           |                       |                       |
           v                       v                       v
    ┌─────────────┐        ┌──────────────┐        ┌─────────────┐
    | Run RMSD,   |        | 1. Clean PDB |        | 1. Clean    |
    | RMSF, etc.  |        | 2. Topology  |        |    PDB      |
    |             |        | 3. Solv/Ions |        | 2. Validate |
    └─────────────┘        └──────────────┘        └─────────────┘
           |                       |                       |
           v                       v                       v
    ┌─────────────┐        ┌──────────────┐        ┌─────────────┐
    | Analysis    |        | Setup        |        | Preprocess  |
    | Report &    |        | Report &     |        | Report &    |
    | Figures     |        | Top/Coord/   |        | Cleaned PDB |
    |             |        | MDP          |        |             |
    └─────────────┘        └──────────────┘        └─────────────┘
```

---

## Detailed Supervisor Decision Tree

```
┌─────────────────────────────────────┐
│         User Goal Received          │
└──────────────────┬──────────────────┘
                   |
                   v
         ┌─────────────────────┐
         | detect_subtask_type |
         └──────────┬──────────┘
                    |
        ┌───────────┼───────────┐
        |           |           |
        v           v           v
    "analysis_ "setup_"prep_     None
     only"      only"  only"   (full)
        |           |           |
        ├─────┬─────┴───┬───────┤
        |     |         |       |
        v  YES v         v       v
    NO PDB    PDB     PDB     PDB
    validation validation validation
        |         |       |       |
        v         v       v       v
        |         |       |       |
    Validate Extract Extract Extract
    Traj      PDB     PDB     PDB
    Paths     Analysis Analysis Analysis
        |         |       |       |
        v         v       v       v
        └─────────┴───────┴───────┘
                  |
                  v
         ┌──────────────────┐
         | Route to Planner |
         └──────────────────┘
                  |
                  v
    ┌─────────────────────────┐
    | Planner detects         |
    | subtask_type in state   |
    └────────────┬────────────┘
                 |
         ┌───────┼───────┐
         |       |       |
         v       v       v
    Analysis Setup Preprocess Full
     Only     Only   Only    Pipeline
         |       |       |       |
         v       v       v       v
    Plan with Plan with Plan Plan
    ONLY     Preprocessing with full
    Analysis + Setup   ONLY  agents
                       Preprocess
```

---

## Input Validation Flow

```
┌─────────────────────────────────────┐
│    Subtask Type Detected            │
└──────────────┬──────────────────────┘
               |
               v
    ┌──────────────────────────┐
    | Check required_inputs    |
    | for this subtask         |
    └──────────────┬───────────┘
               |
   ┌───────────┼───────────────┐
   |           |               |
   v           v               v
analysis_    setup_        preprocess_
only         only          only
   |           |               |
   v           v               v
pdb_req=False  pdb_req=True   pdb_req=True
traj_req=True  analysis_req=True
   |           |               |
   v           v               v
Extract PDB Validate    Validate
Traj Paths  Structure   Structure
   |        + Analysis   + Analysis
   v           |           |
Validate        v           v
Paths        Continue    Continue
   |           |           |
   └───────────┴───────────┘
        |
        v
   Route to Planner
```

---

## Fallback Plan Generation Logic

```
┌──────────────────────────────┐
│  _create_fallback_plan()     │
└─────────────┬────────────────┘
              |
    ┌─────────┴─────────┐
    |                   |
    v                   v
Check subtask_type   Use pdb_analysis
              |
    ┌─────────┼─────────┬──────────┐
    |         |         |          |
    v         v         v          v
analysis_  setup_  preprocess_  (None)
 only      only    only       Full
    |         |       |         |
    v         v       v         v
    |    PREPROCESS   |         |
    |    OPTIONAL     |         |
    |         |       |         |
    v         v       v         v
    |    SETUP        |    PREPROCESS (if needed)
    |         |       v       |
    v         v       v       v
    |       SKIP    DONE   SETUP
    |     HPC & ANALYSIS
    |         |             |
    v         v             v
ANALYSIS    OUTPUTS:      HPC (if requested)
 ONLY     Topology        |
    |     Coords          v
    |     MDPs          ANALYSIS (if requested)
    |       |             |
    v       v             v
OUTPUT   RETURN       RETURN
Report   Setup Plan   Full Plan
Analysis
```

---

## State Flow Through Workflow

```
Initial State
    |
    v
SUPERVISOR
    + subtask_type: detect from goal
    + required_inputs: determine inputs needed
    + trajectory_paths: extract traj files (if analysis-only)
    + analysis_validated: mark validation status
    |
    v
INPUT_VALIDATION (if needed)
    + pdb_analysis: analyze structure (skip for analysis-only)
    + component_selection: parse user intent
    + structured_prompt: create enriched prompt
    |
    v
PLANNER
    + execution_plan: create subtask-aware plan
    + agent_sequence: which agents to run
    |
    v
FIELD AGENTS (varies by subtask)
    
    Analysis-Only:
    └─> ANALYSIS AGENT only
        + analysis_results
        + figures
        + conclusions
    
    Setup-Only:
    └─> PREPROCESSING AGENT (optional)
    └─> SETUP AGENT
        + topology
        + coordinates
        + mdp_files
        + setup_report
    
    Preprocess-Only:
    └─> PREPROCESSING AGENT
        + cleaned_pdb
        + preprocessing_report
    
    Full Pipeline:
    └─> PREPROCESSING AGENT
    └─> SETUP AGENT
    └─> HPC AGENT
    └─> ANALYSIS AGENT
        + All outputs combined
    |
    v
FINAL_REPORT
    + Aggregated results
    + All generated files
    + Summary report
```

---

## Agent Execution Bypass Logic

```
SUPERVISOR._assign_field_agent_tasks()

For each step in plan:
    |
    ├─> If agent = "preprocessing":
    │   └─> Run PREPROCESSING AGENT
    │
    ├─> If agent = "setup":
    │   └─> Run SETUP AGENT
    │
    ├─> If agent = "hpc":
    │   ├─> Check if user explicitly excluded HPC
    │   ├─> If excluded: SKIP, log warning
    │   └─> Otherwise: Run HPC AGENT (first attempt only)
    │
    └─> If agent = "analysis":
        ├─> Check if subtask_type = "analysis_only"
        ├─> If yes: Run ANALYSIS AGENT with trajectory paths
        ├─> If no: Run ANALYSIS AGENT with trajectory from HPC
        └─> Handle failures gracefully

After execution:
    - Increment current_step
    - Check if all steps complete
    - If yes: Route to final_report
    - If no: Return to supervisor for next step
```

---

## Pattern Matching Examples

### Analysis-Only Recognition

```
User Input:
"The simulation production is already done and data output is 
 stored in working_dir/hpc. Please dont preprocess, do not setup 
 simulation and do not job submit the simulation. Only use the 
 analysis agent for simulation analysis for RMSF calculation of 
 trajectory."

Pattern Matching:
✓ Has analysis phrase: "analysis", "RMSF calculation"
✓ Has exclusion phrase: "dont preprocess", "do not setup", "do not job submit"
✓ combination triggers: subtask_type = "analysis_only"

Result:
- Supervisor SKIPS PDB validation
- Planner creates ANALYSIS-ONLY plan
- Only Analysis Agent executes
```

### Setup-Only Recognition

```
User Input:
"Set up MD simulation for my protein in working_dir/protein.pdb. 
 I need topology and coordinate files. Setup only - please do not 
 submit to HPC"

Pattern Matching:
✓ Has setup phrase: "Set up", "topology"
✓ Has HPC exclusion: "do not submit to HPC"
✓ combination triggers: subtask_type = "setup_only"

Result:
- Supervisor validates PDB
- Planner creates SETUP-ONLY plan (preprocessing + setup)
- HPC and Analysis agents SKIPPED
```

---

## Code Entry Points

```
run_agenticAIWork.py
    |
    v
MDWorkflow.run_with_human_feedback()
    |
    v
LangGraph StateGraph Execution
    |
    ├─> supervisor_node()
    │   ├─> detect_subtask_type()
    │   ├─> detect_task_required_inputs()
    │   ├─> detect_trajectory_paths()
    │   └─> _validate_analysis_inputs() [if analysis-only]
    │
    ├─> input_validation_node() [if PDB required]
    │
    ├─> planner_node()
    │   ├─> _create_plan_from_analysis()
    │   ├─> _build_planning_prompt()
    │   └─> _create_fallback_plan() [subtask-aware]
    │
    ├─> field_agent_nodes() [varies by subtask]
    │   ├─> preprocess_node()
    │   ├─> setup_node()
    │   ├─> hpc_node()
    │   └─> analysis_node()
    │
    └─> final_report_node()
```

---

## Summary

The new subtask-specific workflow system provides:

1. **Automatic Detection** - Natural language pattern matching
2. **Flexible Validation** - Only validate required inputs
3. **Intelligent Planning** - Subtask-aware execution plans
4. **Agent Filtering** - Skip unnecessary agents
5. **Backward Compatible** - Full pipeline unchanged
6. **User-Friendly** - No new CLI arguments needed

All while maintaining the original architecture and design patterns.
