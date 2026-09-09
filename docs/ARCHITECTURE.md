# Architecture

**This file is the system design.** It describes how AgenticAI is wired:
the LangGraph hub-and-spoke, the ordered pipeline, multi-simulation layout,
shared `MDState`, and what each agent does. Read it to understand *how a run
moves through the graph*, not how to invoke the CLI or how an RMSD is
computed.

**In this file:** high-level graph, pipeline order, multi-sim directories,
structure acquisition, graph nodes, state fields, per-agent mechanisms, HITL
plan edits, run summary, utilities, a short CLI reminder, recursion limit.

**Not in this file:** coding rules ([CONVENTIONS.md](CONVENTIONS.md)),
dependency versions and GROMACS workarounds ([TOOLS.md](TOOLS.md)), analysis
observables ([ANALYSIS_TOOLS.md](ANALYSIS_TOOLS.md)), worker/SLURM
concurrency ([POOLS.md](POOLS.md)), product overview ([PROJECT.md](PROJECT.md)),
step-by-step run map with flag examples ([PIPELINE_WORKFLOW.md](PIPELINE_WORKFLOW.md)).

---

## High-Level Design

AgenticAI uses a **LangGraph StateGraph** with a hub-and-spoke topology.
Every field agent returns control to the **Supervisor**, which decides the
next step by reading the `next_node` field in shared state.

```
                       ┌──────────────────────┐
   User goal ─────────►│      SUPERVISOR       │◄─── (all agents return here)
   PDB / UniProt ──────►│   (MDSupervisor)      │
                        └──┬──────┬────────┬───┘
                           │      │        │
              ┌────────────┘      │        └─────────────┐
              │                   │                      │
       ┌──────▼──────┐    ┌───────▼──────┐     ┌────────▼──────┐
       │   PLANNER   │    │ FIELD AGENTS │     │   REPORTER    │
       │ (MDPlanner) │    │ (in order)   │     │(ReporterAgent)│
       └──────┬──────┘    └───────┬──────┘     └───────────────┘
              │                   │
       ┌──────▼──────┐    ┌───────▼──────┐
       │ PROGRAMMER  │    │    Human     │
       │(MDProgrammer│    │  Checkpoint  │
       │  internal)  │    │  (optional)  │
       └─────────────┘    └──────────────┘
```

## Workflow Pipeline (Strict Order)

```
Input Validation → Supervisor → Planner →
  Preprocessing → [Human Check] →
  Simulation Setup → [Human Check] →
  HPC Submission → [Human Check] →
  Analysis → Reporter → Final Report
           └──────────────────────────────────►  run_summary.md / .json
```

Human Checks are optional. Enable with **`--HITL all`** (every checkpoint) or
**`--HITL error`** (failures only). Default: fully automatic.
`run_summary.md` and `run_summary.json` are always written to the base
working directory at workflow exit.

Goal + command examples, directory trees, and how flags change what is
written: [PIPELINE_WORKFLOW.md](PIPELINE_WORKFLOW.md).

## Multi-Simulation Mode

When the user supplies multiple PDB files, or requests **multiple component
cases from the same structure** (e.g. protein-only and protein+ATP+MG from
one AlphaFold model), the Supervisor orchestrates the simulations internally
by looping over `sim_prompts`.

```
SimAgent.py --working-dir ./study
  │
  └─ Supervisor builds master plan
       ├─ sim_prompts[0]: label=p21860,       case=protein-only
       ├─ sim_prompts[1]: label=p21860_ATP_MG, case=holo
       │     (feasibility guard: skip holo if ligand/ion absent)
       │
       ├─ Per-sim work under {base}/{label}/ (parallel when HITL is off):
       │     prep (local workers) → HPC pool (SLURM) → analysis/reporter
       │
       └─ Combined analysis at base_dir/ (only if N>1):
            ├─ overlay plots (RMSD, RMSF, Rg, energy, COM distance)
            ├─ DCCM panels + apo–holo DCCM difference
            ├─ segment RMSF bars (user-defined residue windows)
            ├─ statistical_summary.json
            └─ combined_report.html  (Reporter)
```

Worker counts and SLURM slots: [POOLS.md](POOLS.md).

### Directory Layout

```
base_dir/
    p21860/                     # per-sim isolated working directory
        preprocess/             # cleaned PDB, domain-trimmed PDB
        simsetup/               # topology, coordinates, MDP files, chain_residue_map.json
        hpc/                    # SLURM script, trajectories
        analysis/               # plots, CSVs, summary JSON
        reporter/               # per-sim HTML report
        planner/                # execution_plan.md/json
        supervisor/             # execution_report.md, state.jsonl
        agent_conversation.log
    p21860_ATP_MG/
        ...                     # (or skip reason if feasibility failed)
    analysis/                   # combined analysis outputs
    combinedAnalysis/           # alternate combined output location
    reporter/
        combined_report.html    # cross-simulation comparison report
    planner/
        master_plan.md          # multi-sim plan with per-case prompts
        master_plan.json
    supervisor/
        state.jsonl
        execution_report.md
    agent_conversation.log      # full run log
    run_summary.md              # human-readable run outcome table
    run_summary.json            # structured run outcome data
```

### Isolation and concurrency

Each simulation has its own `{base}/{label}/` tree and a reset copy of
per-sim `MDState` fields. Combined analysis and HITL stay sequential.
Prep and post-HPC analysis/reporter can run as a **local worker pool**;
production MD uses the **SLURM HPC pool** ([POOLS.md](POOLS.md)).
The shared `LLMClient` is stateless at the HTTP level. PDB files are copied
into per-sim directories before each sim starts.

## Structure Acquisition Pipeline

When a UniProt accession is provided instead of a local PDB file, the
following pipeline runs inside the Preprocessing agent:

```
User goal: "UniProt P21860, kinase domain"
  │
  v
structure_request_parser  (src/preprocess/structure_request_parser.py)
  → uniprot_id=P21860, domain="kinase domain"
  │
  v
structure_sources registry  (src/preprocess/structure_sources/)
  ├─ AlphaFold API (default)
  └─ RCSB PDB (fallback)
  │
  v
domain_sources  (src/preprocess/domain_sources/)
  → UniProt REST API → residue range 709–966
  │
  v
extract_domain  (src/preprocess/domain_extractor.py)
  → ERBB3_kinase_domain.pdb
  │
  v
structure_validator  (src/preprocess/structure_validator.py)
  → missing residues check, Ca-Ca break check (>4.5 A)
  │
  v
Preprocessing agent  → cleaned_pdb
```

## Graph Nodes

The LangGraph registers **12 nodes**:

| Node | Class / module | Purpose |
|------|---------------|---------|
| `input_validation` | `supervisor_agent.py` + `input_validator.py` | Parse goal, resolve UniProt, domain lookup, feasibility check |
| `supervisor` | `MDSupervisor` | Prompt enrichment, routing, multi-sim orchestration |
| `planner` | `MDPlanner` | Auto-discover tools, load knowledge, build execution plan |
| `preprocess` | `PreprocessingAgent` | Download/extract domain, clean PDB, add H, separate components |
| `setup` | `SimulationSetupAgent` | Topology, solvation, ions, MDP files, ACPYPE for ligands |
| `hpc` | `MDHPCAgent` | SLURM script, SSH submit, job monitor, result download |
| `analysis` | `MDAnalysisAgent` | RMSD/RMSF/Rg/DCCM/DSSP + combined overlays + DCCM diff |
| `reporter` | `ReporterAgent` | HTML report, literature, 3D viewer, LLM narrative |
| `human_preprocess_check` | `human_checkpoints.py` | Optional approval after preprocessing |
| `human_setup_check` | (same) | Optional approval after setup |
| `human_hpc_check` | (same) | Optional approval after HPC |
| `final_report` | `workflow.py` | Terminal node → END |

## State Management

All data flows through a single **`MDState`** TypedDict (`agentic/state.py`, ~65 fields).

### Naming Convention

Fields follow the pattern `{stage}_{artifact}`:

| Field | Populated by | Content |
|-------|-------------|---------|
| `raw_pdb` | CLI / input_validation | Original PDB path |
| `cleaned_pdb` | Preprocessing | Protonated, separated PDB |
| `topology` | SimSetup | GROMACS `.top` path |
| `coordinates` | SimSetup | Solvated `.gro` path |
| `chain_residue_map` | SimSetup | PDB chain+resid → trajectory `resindex` JSON |
| `trajectory_path` | HPC | Downloaded `.xtc` trajectory |
| `analysis_results` | Analysis | Dict of observables and plot paths |
| `reporter_output` | Reporter | Path to generated HTML |
| `structure_request` | input_validation | UniProt ID, domain label, residue range |
| `domain_context` | input_validation | Human-readable domain summary string |
| `sim_case` | Supervisor | Current component case (e.g. `protein+ATP+MG`) |
| `completed_sim_states` | Supervisor | List of per-sim snapshots (status, job_id, errors) |

### Control-Flow Fields

| Field | Role |
|-------|------|
| `next_node` | Tells supervisor where to route next |
| `current_node` | Set by `_wrap_node()` for tracking |
| `execution_plan` | Planner-generated task list |
| `current_step` | Index into `execution_plan` |
| `errors` / `warnings` | Accumulated issue lists |
| `human_feedback` | Response from human checkpoint |
| `is_multi_simulation` | True when sim_prompts has >1 entry |
| `sim_prompts` | List of per-simulation goal dicts |
| `multi_sim_phase` | `per_sim` → `combined_analysis` → `combined_reporter` |

### Per-Agent Directories and File Management

Each agent writes to its own subdirectory managed by `SecureFileManager`:

```
working_dir/
    preprocess/     # cleaned PDB, domain-trimmed PDB, logs
    simsetup/       # topology, coordinates, MDP files, chain_residue_map.json
    hpc/            # {job_name}_run.sh, trajectories, energy files
    analysis/       # plots, CSVs, analysis_summary.json
    reporter/       # HTML report, images
    planner/        # execution_plan.md, execution_plan.json
    supervisor/     # execution_report.md, state.jsonl
```

`SecureFileManager` sanitises filenames, prevents path traversal, and
records every generated file in a centralised **file registry** (type,
description, producing agent, timestamp). The registry allows downstream
agents to discover upstream outputs without hardcoded paths.

## Agent Details

### Supervisor (`MDSupervisor`)

Responsibilities:
1. Parse UniProt IDs and domain labels from goal text
2. Query UniProt REST API for domain residue boundaries
3. Single LLM enrichment call → `structured_prompt`
4. Build `master_plan.md` + `sim_prompts` for multi-sim
5. Route agents in strict order; retry after human feedback
6. Feasibility guard: skip holo cases when ligand/ion absent in source structure
7. Record `completed_sim_states` snapshots per simulation

Config: `agentic/supervisor/config.yaml`

### Planner (`MDPlanner`)

1. Auto-discovers all `@tool` functions from every agent's `tools.py`
2. Loads domain knowledge from `agentic/planner/knowledge/`
3. Submits tools + knowledge + goal to LLM → execution plan
4. Extracts per-agent instruction blocks into state fields:
   `preprocessing_instructions`, `setup_instructions`,
   `hpc_instructions`, `analysis_instructions`, `reporter_instructions`
5. Invokes `MDProgrammer` internally for code generation gaps
6. Persists plan to `planner/execution_plan.md`, `execution_plan.json`,
   `execution_plans.jsonl`

### Programmer (`MDProgrammer`)

- Called internally by Planner only (never by Supervisor)
- Generates Python `@tool` functions, TCL scripts, MDP files, SLURM scripts
- Validates syntax before registering in the live tool library

### Preprocessing Agent (`PreprocessingAgent`)

Tools (auto-discovered by Planner):

| Tool | Function |
|------|----------|
| `acquire_protein_structure` | End-to-end: download → domain trim → validate |
| `lookup_domain_range_tool` | UniProt REST domain boundary lookup |
| `download_structure` | Fetch AlphaFold or RCSB PDB |
| `extract_domain` | Trim PDB to residue span |
| `analyze_pdb` | Count atoms, chains, residues, ligands |
| `separate_complex_components` | Split protein/ligand/ion into PDB files |
| `add_hydrogens` | PDB2PQR + PROPKA (pH 7.0 default) |
| `validate_structure` | Missing residues, broken backbone check |

Key mechanisms:
- **File alias map**: generic references (`ligand.pdb`) → actual outputs (`ATP_h.pdb`)
- **Domain trimming**: applied when `structure_request` contains residue range
- **Phospho + multi-chain PDB order**: keep SEP/TPO/PTR on the protein, sort by
  chain/resid, insert `TER` for `pdb2gmx` C-termini (not the trajectory chain
  map). See [TOOLS.md](TOOLS.md#phosphorylation-and-chain-order-in-the-pdb-not-this-map).

### Simulation Setup Agent (`SimulationSetupAgent`)

Key mechanisms:
- GROMACS `pdb2gmx`, solvation, `genion`, MDP generation
- ACPYPE/AmberTools for non-standard ligand parameterisation
- **ACPYPE moleculetype resolution**: reads `[ moleculetype ]` directly from
  ITP file to align `[ molecules ]` entries — avoids `moleculetype not found`
- **Multi-chain residue map**: after `pdb2gmx`, write
  `chain_residue_map.json` so analysis can translate `chainID B and resid 50:75`
  onto trajectory `resindex` (GROMACS TPR/GRO/XTC have no chain IDs). See
  [TOOLS.md](TOOLS.md#multi-chain-residue-map).
- Retry: failed tool calls retry up to 2× before human escalation

### HPC Agent (`MDHPCAgent`)

Key mechanisms:
- Generates `{job_name}_run.sh` (not `slurm_job.sh` — LLM-hallucinated names ignored)
- Script path resolved from `state["job_script"]` or `{job_name}_run.sh` pattern
- SSH submit via Paramiko; Singularity containers on compute nodes
- Job wait is owned by the HPC pool (default poll `--hpc-check-interval 2h`);
  analysis reads trajectories from `{sim}/hpc/` on the shared filesystem
  ([POOLS.md](POOLS.md))

### Analysis Agent (`MDAnalysisAgent`)

Operates in two modes:
- **Per-sim**: LLM selects tool subset from `analysis_instructions`
- **Combined**: auto-triggered after all sims; runs cross-sim tools

Key analysis tools:
- `calculate_rmsd`, `calculate_rmsf`, `calculate_radius_of_gyration`
- `calculate_dccm`, `plot_dccm_difference` (apo–holo)
- `run_combined_rmsf_segment_analysis` (user residue window)
- `run_combined_com_distance_analysis` (ATP pocket stability)
- `analyze_secondary_structure` (DSSP whole + segments)
- `compute_comparison_table` → `statistical_summary.json`

**Multi-chain selections:** the LLM still writes PDB-style `chainID` /
`resid` strings. A translator in `TrajectorySession` / `AnalysisToolExecutor`
rewrites them to `resindex` using `simsetup/chain_residue_map.json`. Details:
[TOOLS.md](TOOLS.md#multi-chain-residue-map).

### Reporter Agent (`ReporterAgent`)

Two modes matching Analysis agent (per-sim + combined).

Literature sources (deduplicated by PMID + DOI, max 15 refs):
- PubMed (NCBI Entrez)
- bioRxiv (Europe PMC `SRC:PPR`)
- UniProt functional annotations

HTML report features:
- LLM narrative (rule-based fallback from `analysis_summary.json`)
- 3Dmol.js viewer: diagnostic trajectory snapshots, representation toggles,
  sequence bar, PNG export
- Combined report: overlay figures, comparison table, literature discussion

### Human Checkpoint

Normalises free-text responses via fuzzy phrase matching:
- `approved` → proceed
- `retry` → extract parameters, patch plan, re-execute
- `reject` → stop workflow

Enabled with **`--HITL all`**. With **`--HITL error`**, only failure paths pause.
Default: checkpoints are skipped (fully automatic).

## Planner Detail: Interactive Plan Modification

Uses **sentinel-based protocol** during human-in-the-loop sessions:
- LLM receives current plan + user modification request
- Returns conversational reply OR full updated plan prefixed with
  `PLAN_UPDATE:<agent_key>`
- Brace-counting JSON extractor recovers plan from noisy LLM output
- Regex parameter extractors patch tool parameter dicts directly
  (force field, water model, temperature, pressure, production duration)

## Run Summary

At every workflow exit, `src/utils/run_summary.py` writes:
- `run_summary.md` — human-readable: mode, counts, per-sim table, domain context, errors
- `run_summary.json` — structured data for downstream scripts

The summary counts derive from `len(sim_prompts)` (not `len(pdb_list)`) so
1 source PDB × 2 component cases correctly reports **2 total simulations**.

## Utility Modules

### Chat Tools (`src/utils/chat_tools.py`)

`read_file_tool` (up to 500 lines) with automatic FILE SUMMARY for large files:
- PDB: ATOM + HETATM count, unique residue names
- GRO: atom count; CSV/DAT: data row count

Allows LLM to reason about large files without full token consumption.

### LLM Client (`agentic/llm.py`)

- Tries `ollama` Python package first; falls back to raw HTTP (`requests`)
- Mock mode (`_is_mock_mode`) for offline testing
- Non-streaming `/api/generate` preferred; tolerant of streamed NDJSON
- Config: `agentic/config.json`, `llm_config.py`

## CLI Reference

Common flags (full list: [PROJECT.md](PROJECT.md#cli-reference) and
[README.md](../README.md)):

```
python SimAgent.py \
  --goal "..."                   # Natural-language simulation objective
  --working-dir <dir>            # Base output directory
  --pdb-list A.pdb B.pdb ...    # Explicit PDB list (multi-sim)
  --subtask preprocess simsetup hpcjob analysis reporter
  --no-llm                       # Disable LLM (off by default: LLM on)
  --llm-base-url URL             # Ollama endpoint
  --llm-model gpt-oss:20b        # LLM model name
  --HITL error|all               # Human-in-the-loop (default: off)
  --resume                       # Restore supervisor/state.jsonl and continue
  --allowed-hpc-jobs 5           # Cross-sim HPC pool concurrency
  --hpc-check-interval 2h      # SLURM poll interval during pool wait
  --force-field amber99sb-ildn   # Override force field
  --water-model tip3p            # Override water model
```

When one or more PDB paths (or UniProt IDs) are resolved from `--goal` /
`--pdb-list` / `--sim-dirs`, the Supervisor always uses the campaign tree
`{base}/{label}/`. Combined analysis runs only when `len(sim_prompts) > 1`.

## Recursion Limit

The LangGraph is compiled with `recursion_limit=25` to prevent infinite loops.
