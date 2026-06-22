# Methods

> **Purpose:** Draft Methods section for a high-impact journal manuscript. Describes AgenticAI as an LLM-orchestrated, modular MD workflow framework. Update version numbers and quantitative run parameters (simulation length, cluster name) before submission.

---

## 2.1 System Design: Capability, Modularity, and Extensibility

We developed **AgenticAI**, an autonomous computational framework in which a large language model (LLM) reasons over user intent, structure metadata, and available tools to orchestrate end-to-end molecular dynamics (MD) workflows. The system accepts a natural-language research objective together with zero or more Protein Data Bank (PDB) structures (or a UniProt accession from which a structure is acquired automatically) and produces simulation inputs, trajectories, quantitative analyses, comparative ensemble figures, and an interactive HTML report.

The design prioritises three properties emphasised throughout this work:

| Property | Implementation | Scientific benefit |
|----------|----------------|-------------------|
| **Capability** | End-to-end coverage: structure acquisition → preprocessing → GROMACS setup → HPC submission → trajectory analysis → literature-aware reporting | A single natural-language goal can drive an entire comparative MD study without manual pipeline scripting |
| **Modularity** | Hub-and-spoke LangGraph with specialised field agents; each agent owns an isolated output directory and a tool registry | New analysis modules, structure sources, or HPC backends can be added without rewriting the supervisor |
| **Extensibility** | Registry-based plugins for structure download (`structure_sources/`), domain annotation (`domain_sources/`), and agent tools (`tools.py` auto-discovery) | Domain-specific knowledge (e.g. kinase activation loops) is injected via parsers and knowledge documents rather than hard-coded paths |

### 2.1.1 Architectural overview

Workflow orchestration is implemented in **Python 3.11** using **LangGraph v1.0.7**. A directed `StateGraph` connects 12 nodes. A central **Supervisor** hub routes execution; every field agent returns control to the Supervisor, which reads shared state and sets `next_node`. Inter-agent communication occurs exclusively through a typed shared state object (`MDState`, ~60 fields) following the convention `{stage}_{artifact}` (e.g. `cleaned_pdb`, `trajectory_path`, `analysis_results`).

```
  INPUT
  ┌─────────────────────────┐   ┌──────────────────────┐
  │  Natural-language goal  │   │  PDB / UniProt ID    │
  └────────────┬────────────┘   └──────────┬───────────┘
               └──────────────┬────────────┘
                              │
                   ┌──────────▼───────────┐
                   │   Input Validation    │
                   └──────────┬───────────┘
                              │
                   ┌──────────▼───────────┐     ┌────────────────┐
                   │      SUPERVISOR       │◄────│ Human feedback │
                   │    (hub / router)     │     │  (optional)    │
                   └──┬────┬────┬────┬────┘     └────────────────┘
                      │    │    │    │
           ┌──────────┘    │    │    └──────────────────┐
           │               │    │                       │
  ┌────────▼───────┐       │    │              ┌────────▼────────┐
  │    PLANNER     │       │    │              │    REPORTER     │
  │  (MDPlanner)   │       │    │              │ (ReporterAgent) │
  └────────┬───────┘       │    │              └────────┬────────┘
           │               │    │                       │
  ┌────────▼───────┐       │    │                       │
  │   PROGRAMMER   │       │    │                       │
  │ (MDProgrammer) │       │    │                       │
  └────────────────┘       │    │                       │
                           │    │                       │
          ┌────────────────┘    └────────────┐          │
          │                                  │          │
  ┌───────▼──────────────────────────────────▼───┐      │
  │              FIELD AGENTS (strict order)     │      │
  │                                              │      │
  │  ┌────────────┐    ┌────────────┐            │      │
  │  │Preprocessing│──►│  SimSetup  │            │      │
  │  └─────┬──────┘    └─────┬──────┘            │      │
  │        │ [checkpoint?]   │ [checkpoint?]     │      │
  │        │                 │                   │      │
  │  ┌─────▼──────┐    ┌─────▼──────┐            │      │
  │  │  HPC Agent │    │  Analysis  │────────────┼──────┘
  │  └─────┬──────┘    └────────────┘            │
  │        │ [checkpoint?]                        │
  └────────┼─────────────────────────────────────┘
           │
  ┌────────▼────────┐
  │   FINAL REPORT  │
  └─────────────────┘

  [checkpoint?] = optional human approval gate (--no-human-loop to skip)
  All agents return state to SUPERVISOR before next step.
```

**Novelty relative to conventional MD automation.** Unlike static workflow managers (Snakemake, shell scripts, or notebook pipelines), AgenticAI delegates *scientific planning* and *interpretation* to the LLM while retaining deterministic tool execution for numerically exact operations (GROMACS, MDAnalysis, SLURM). The Planner translates ambiguous goals into dependency-aware execution plans; the Analysis and Reporter agents synthesise biological inferences from quantitative outputs and external literature. Human experts remain optional checkpoints rather than mandatory operators at every stage.

### 2.1.2 Shared state and audit trail

All artifacts are tracked in a centralised **file registry** (type, producing agent, timestamp) so downstream agents discover outputs without path hardcoding. Accumulated `errors` and `warnings` lists provide a running audit trail. At workflow completion, a base-level **`run_summary.json`** / **`run_summary.md`** is written to the working directory, tabulating per-simulation status (success, skipped, failed), domain context, job identifiers, and paths to logs and reports.

| Artifact | Location | Role in manuscript |
|----------|----------|-------------------|
| `agent_conversation.log` | `{working_dir}/` | Full agent dialogue, LLM prompts/responses, routing decisions |
| `planner/execution_plan.md` | per-simulation or base | Planner's structured scientific plan |
| `planner/master_plan.md` | base (multi-sim) | Cross-simulation master plan and combined analysis specification |
| `supervisor/execution_report.md` | per-simulation or base | Stage-by-stage execution summary |
| `run_summary.md` | base | Machine- and human-readable run outcome table |
| `reporter/*.html` | per-sim or `combined_report.html` | Interactive report with figures and LLM narrative |

---

## 2.2 Agent Descriptions

AgenticAI contains **nine specialised agent roles** arranged in a strict hierarchy. The three top-tier orchestrators (Supervisor, Planner, Programmer) handle cognition; the five field agents handle execution; an optional Human Checkpoint agent mediates user approval gates.

```
  ╔══════════════════════════════════════════════════════════════╗
  ║                    ORCHESTRATION TIER                        ║
  ║                                                              ║
  ║   ┌──────────────────────────────────────────────────┐      ║
  ║   │            SUPERVISOR  (MDSupervisor)             │      ║
  ║   │  - Input validation & prompt enrichment           │      ║
  ║   │  - Multi-sim master planning & routing            │      ║
  ║   │  - Holo feasibility guard & case expansion        │      ║
  ║   └──────────┬────────────────────────────────────────┘      ║
  ║              │                                               ║
  ║   ┌──────────▼──────────────┐                               ║
  ║   │   PLANNER  (MDPlanner)  │◄──────────────────────┐       ║
  ║   │  - Auto-discovers tools │                        │       ║
  ║   │  - Loads knowledge base │       returns plan     │       ║
  ║   │  - LLM execution plan   │                        │       ║
  ║   └──────────┬──────────────┘                        │       ║
  ║              │ requests script                        │       ║
  ║   ┌──────────▼──────────────┐                        │       ║
  ║   │ PROGRAMMER (MDProgrammer│────────────────────────┘       ║
  ║   │  - Generates @tool code │                               ║
  ║   │  - TCL / MDP / SLURM    │                               ║
  ║   └─────────────────────────┘                               ║
  ╚══════════════════════════════════════════════════════════════╝

  ╔══════════════════════════════════════════════════════════════╗
  ║                     FIELD AGENT TIER                         ║
  ║                                                              ║
  ║  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐      ║
  ║  │PREPROCESSING │  │   SIMSETUP   │  │     HPC      │      ║
  ║  │PreprocessAgent│  │SimSetupAgent │  │ MDHPCAgent   │      ║
  ║  │- download PDB│  │- pdb2gmx     │  │- SLURM script│      ║
  ║  │- domain trim │  │- solvate     │  │- SSH submit  │      ║
  ║  │- add H atoms │  │- ACPYPE      │  │- job monitor │      ║
  ║  │- validate    │  │- MDP files   │  │- download    │      ║
  ║  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘      ║
  ║         │ [checkpoint?]   │ [checkpoint?]   │ [checkpoint?]║
  ║                                                              ║
  ║  ┌──────────────────────────┐  ┌────────────────────────┐  ║
  ║  │       ANALYSIS           │  │       REPORTER         │  ║
  ║  │    MDAnalysisAgent       │  │    ReporterAgent       │  ║
  ║  │- RMSD / RMSF / Rg        │  │- PubMed / bioRxiv      │  ║
  ║  │- DCCM + DCCM difference  │  │- LLM narrative         │  ║
  ║  │- Segment RMSF / DSSP     │  │- 3Dmol.js viewer       │  ║
  ║  │- COM pocket distance     │  │- HTML report           │  ║
  ║  │- Combined overlays       │  │- Combined report       │  ║
  ║  └──────────────────────────┘  └────────────────────────┘  ║
  ╚══════════════════════════════════════════════════════════════╝

  ╔══════════════════════════════════╗
  ║     OPTIONAL HUMAN CHECKPOINT    ║
  ║  fuzzy-match: approved / retry / ║
  ║  reject  ·  param extraction     ║
  ╚══════════════════════════════════╝
```

### 2.2.1 Supervisor (`agentic/supervisor/supervisor_agent.py`)

**Class:** `MDSupervisor` | **LLM temperature:** 0.1

The Supervisor is the central controller and the sole node that the LangGraph routing mechanism consults at each step. It does not execute any MD tasks directly. Its responsibilities are:

1. **Input validation** — calls `input_validator.py` to parse the user goal, resolve UniProt accessions, query domain residue ranges from UniProt, and check feasibility (e.g. whether requested ligands exist in the source structure).
2. **Prompt enrichment** — a single LLM call via `unified_enricher.py` translates the raw natural-language goal into a structured `structured_prompt` under fixed simulation defaults (amber99sb-ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl, 1.2 nm cubic box).
3. **Multi-simulation master planning** — generates `master_plan.md` with per-simulation prompts and a combined analysis plan when multiple component cases or PDB files are detected.
4. **Routing decisions** — reads `next_node` from state and directs execution in strict pipeline order; re-routes on retry after human feedback.
5. **Component case expansion** — from a single AlphaFold PDB, expands `sim_prompts` for e.g. `protein-only` and `protein+ATP+MG` cases; records `completed_sim_states` snapshots including skip reasons.
6. **Holo feasibility guard** — calls `validate_sim_case_components` to skip holo cases when the source structure lacks required ligands/ions, logging the reason rather than failing silently.

**Key state fields read:** `user_goal`, `raw_pdb`, `pdb_analysis`, `structure_request`, `domain_context`  
**Key state fields written:** `structured_prompt`, `sim_prompts`, `master_plan`, `next_node`, `completed_sim_states`

---

### 2.2.2 Planner (`agentic/planner/planner_agent.py`)

**Class:** `MDPlanner` | Has internal `MDProgrammer`

The Planner translates the Supervisor's enriched prompt into a concrete, dependency-aware execution plan. It is the primary site of **scientific reasoning** in the framework.

On invocation the Planner:

1. **Discovers all available tools** via `tools_registry.py` — auto-introspects `tools.py` in every agent package to build a live catalogue of callable functions with signatures, descriptions, and expected outputs.
2. **Loads domain knowledge** via `knowledge_loader.py` — reads Markdown, JSON, and PDF documents from `agentic/planner/knowledge/` covering MD protocols, force field parameters, and HPC best practices.
3. **Submits a composite prompt** to the LLM containing: tool catalogue, knowledge context, enriched user goal, and simulation state. The LLM returns a natural-language execution plan structured as numbered agent-specific sections.
4. **Extracts per-agent instruction blocks** (`preprocessing_instructions`, `setup_instructions`, `hpc_instructions`, `analysis_instructions`, `reporter_instructions`) from the full plan and writes them to state for each field agent to read.
5. **Invokes the Programmer** internally when a plan step requires a script or tool not in the existing library.

The Planner persists its output to `{working_dir}/planner/execution_plan.md`, `execution_plan.json`, and `execution_plans.jsonl` for audit and manuscript snapshots.

**Key inference outputs:**
- Explicit step-by-step MD protocol with biological rationale
- Analysis metrics list derived from goal semantics (e.g. DCCM difference between apo/holo when both cases are planned)
- Segment RMSF window specification from activation-loop mentions in natural language
- Literature retrieval scope for the Reporter

---

### 2.2.3 Programmer (`agentic/programmer/programmer_agent.py`)

**Class:** `MDProgrammer` | Called internally by Planner

The Programmer is a code-generation sub-agent invoked when the Planner identifies a gap in the existing tool library. It generates:

- **Python tools** (LangChain `@tool`-decorated functions) for custom analysis or processing
- **TCL scripts** for VMD/NAMD visualisation or trajectory operations
- **GROMACS MDP files** with non-standard parameter sets
- **SLURM batch scripts** for new HPC resource profiles

Generated code is syntax-validated before being registered in the live tool library, extending the framework's capability at runtime. The Programmer is never called by the Supervisor directly; it is an implementation detail of the Planner.

---

### 2.2.4 Preprocessing Agent (`agentic/preprocess/preprocessing_agent.py`)

**Class:** `PreprocessingAgent`

Responsible for converting raw input coordinates into clean, simulation-ready structures. Executes in `working_dir/{label}/preprocess/`.

**Tool set:**

| Tool | Function |
|------|----------|
| `acquire_protein_structure` | End-to-end: download → extract domain → validate |
| `lookup_domain_range_tool` | Query UniProt REST API for named domain residue boundaries |
| `download_structure` | Fetch AlphaFold or RCSB PDB by accession |
| `extract_domain` | Trim PDB to specified residue span (BioPython / MDAnalysis) |
| `analyze_pdb` | Count atoms, chains, residue types, ligands, water |
| `separate_complex_components` | Split protein/ligand/ion into individual PDB files |
| `add_hydrogens` | PDB2PQR + PROPKA pKₐ-based protonation (pH 7.0 default) |
| `validate_structure` | Check missing residues, broken backbone (Cα–Cα > 4.5 Å) |

**Workflow logic:** The agent reads `preprocessing_instructions` from state (Planner output), selects tools accordingly (LLM-guided plan within the agent), applies `_apply_domain_trim_if_requested` when `structure_request` contains a residue range, and maintains a **file alias map** to resolve generic plan references (`ligand.pdb`) to actual output filenames (`ATP_h.pdb`).

**Key state fields:** `raw_pdb` → `cleaned_pdb`, `structure_request`, `domain_context`

---

### 2.2.5 Simulation Setup Agent (`agentic/simsetup/setup_agent.py`)

**Class:** `SimulationSetupAgent`

Constructs the complete GROMACS simulation system from preprocessed coordinates. Executes in `working_dir/{label}/simsetup/`.

**Tool set:**

| Tool | Function |
|------|----------|
| `build_topology` | `pdb2gmx` — assign AMBER99SB-ILDN force field, generate `.top` |
| `generate_ligand_parameters` | ACPYPE + `antechamber` — GAFF topology for non-standard ligands |
| `convert_amber_to_gromacs` | ParmEd — convert AmberTools output to GROMACS format |
| `build_simulation_box` | `editconf` — define cubic/dodecahedral box with buffer |
| `solvate_system` | `solvate` — add TIP3P water |
| `add_ions` | `genion` — neutralise charge, add NaCl to target concentration |
| `generate_mdp_files` | Write MDP files for minimisation, NVT, NPT, production |

**ACPYPE moleculetype resolution:** reads the `[ moleculetype ]` section directly from the generated ITP to align GROMACS `[ molecules ]` entries with ACPYPE output names (e.g. `ATP_h`), avoiding `moleculetype not found` errors. Failed tool calls retry up to twice before escalating to human checkpoint.

**Key state fields:** `cleaned_pdb` → `topology`, `coordinates`, `mdp_files`

---

### 2.2.6 HPC Agent (`agentic/hpc/hpc_agent.py`)

**Class:** `MDHPCAgent`

Manages the full lifecycle of high-performance computing jobs: script generation, submission, monitoring, and result download.

**Workflow:**
1. Copy simulation files from `simsetup/` to `hpc/`
2. Estimate wall-time based on atom count and simulation duration
3. Generate SLURM batch script (`{job_name}_run.sh`) using Singularity containers
4. Submit via SSH (Paramiko); retry up to 2 times on transient errors
5. Poll job status hourly via `check_job_status`
6. Download trajectory (`.xtc`), energy (`.edr`), and log (`.log`) on completion

**Script path resolution fix:** ignores LLM-hallucinated filenames (e.g. `slurm_job.sh`) and always uses `state["job_script"]` or the pattern `{job_name}_run.sh`, preventing `sbatch: error: script not found` failures.

**Key state fields:** `topology`, `coordinates`, `mdp_files` → `job_id`, `job_status`, `trajectory_path`

---

### 2.2.7 Analysis Agent (`agentic/analysis/analysis_agent.py`)

**Class:** `MDAnalysisAgent`

Performs trajectory analysis using **MDAnalysis v2.10.0** as the primary library. The agent operates in two modes:

- **Per-simulation mode:** LLM reads `analysis_instructions` and selects the relevant subset of tools for the current goal.
- **Combined multi-simulation mode:** triggered automatically after all per-simulation pipelines complete; generates overlay plots, DCCM difference matrices, segment RMSF bars, COM distance overlays, and a statistical summary table across all simulation labels.

**Tool set (selected):**

| Tool | Observable |
|------|------------|
| `calculate_rmsd` | Backbone Cα RMSD relative to reference |
| `calculate_rmsf` | Per-residue root-mean-square fluctuation |
| `calculate_radius_of_gyration` | Global compactness |
| `calculate_com_distance` / `calculate_ligand_pocket_distance` | ATP-to-pocket binding stability |
| `calculate_dccm` | Dynamic cross-correlation matrix (Cα) |
| `plot_dccm_difference` | Element-wise apo–holo DCCM difference |
| `run_combined_rmsf_segment_analysis` | RMSF bar chart for user-defined residue window |
| `run_combined_com_distance_analysis` | Multi-system COM distance overlay |
| `run_combined_dccm_difference` | Cross-system DCCM difference |
| `analyze_secondary_structure` | DSSP time evolution (full protein and segments) |
| `compute_comparison_table` | Statistical summary JSON across simulation labels |
| `run_combined_dccm_analysis` | DCCM panels for all simulations |

**LLM inference role:** metric selection is not hard-coded. The LLM reads the analysis instructions and goal semantics to decide which tools to call and in what order, enabling goal-specific analysis plans without configuration files.

**Key state fields:** `trajectory_path`, `topology` → `analysis_results`

---

### 2.2.8 Reporter Agent (`agentic/reporter/reporter_agent.py`)

**Class:** `ReporterAgent`

Produces the final deliverable: a self-contained interactive HTML report. Operates in two modes matching the Analysis agent:

- **Per-simulation mode:** generates a single-system report with embedded figures, 3D viewer, and LLM narrative.
- **Combined multi-simulation mode:** generates `combined_report.html` integrating per-simulation summaries, overlay figures, a comparison table, and a literature-correlated discussion.

**Tool set:**

| Tool | Function |
|------|----------|
| `search_pubmed_literature` | BioPython Entrez — retrieve PubMed abstracts |
| `search_biorxiv_literature` | Europe PMC REST API (`SRC:PPR`) — preprints |
| `search_uniprot_annotations` | UniProt REST API — protein function, PTMs, disease variants |
| `generate_html_report` | Assemble full self-contained HTML with embedded CSS/JS |
| `extract_pdb_for_viewer` | Select best available coordinate file for 3D viewer |

**Scientific inference outputs:**
- **Literature review:** deduplicated (PMID + DOI) across three sources (max 15 refs), merged into a narrative linking simulation observables to published biology
- **LLM narrative:** interprets quantitative metrics (RMSD plateau, high-RMSF residues, DCCM blocks) in biological context; rule-based fallback synthesises observations from `analysis_summary.json` when LLM unavailable
- **3Dmol.js viewer:** trajectory snapshots at diagnostic frames (max-RMSD, ligand approach events) with multi-representation toggles, surface rendering, sequence bar, and PNG export
- **Final impression:** cross-study conclusion paragraph generated by LLM

**Key state fields:** `analysis_results`, `trajectory_path`, `cleaned_pdb` → `reporter_output`

---

### 2.2.9 Human Checkpoint (`agentic/human_checkpoints.py`)

Optional approval gate inserted after preprocessing, simulation setup, and HPC completion. Normalises free-text user responses via fuzzy phrase matching (`approved` / `retry` / `reject`). On `retry`, regex-based parameter extractors patch the updated plan with new simulation parameters before re-routing. The checkpoints are disabled with `--no-human-loop` for fully automatic execution.

---

### 2.2.10 Agent interaction and data flow

The following table summarises how agents exchange data through `MDState`:

| Stage | Agent | Reads from state | Writes to state |
|-------|-------|-----------------|-----------------|
| Validation | Supervisor | `user_goal`, `raw_pdb` | `structured_prompt`, `pdb_analysis`, `structure_request` |
| Planning | Planner | `structured_prompt`, `sim_prompts` | `execution_plan`, `*_instructions` fields |
| Code generation | Programmer | `execution_plan` | New `@tool` registrations |
| Structure prep | Preprocessing | `raw_pdb`, `structure_request`, `preprocessing_instructions` | `cleaned_pdb`, `domain_context`, `file_registry` |
| MD setup | SimSetup | `cleaned_pdb`, `setup_instructions` | `topology`, `coordinates`, `mdp_files` |
| HPC | HPC | `topology`, `coordinates`, `mdp_files` | `job_id`, `job_status`, `trajectory_path` |
| Analysis | Analysis | `trajectory_path`, `topology`, `analysis_instructions` | `analysis_results` |
| Reporting | Reporter | `analysis_results`, `trajectory_path`, `cleaned_pdb` | `reporter_output` |

---

## 2.3 LLM Reasoning Across Agents

Agents use the local LLM server (**Ollama**; model `gpt-oss:20b`) at four distinct reasoning levels. All calls include deterministic fallbacks.

| Agent | LLM call purpose | Output used for |
|-------|-----------------|-----------------|
| Supervisor | Prompt enrichment; feasibility validation; master plan composition | `structured_prompt`, `sim_prompts`, routing decisions |
| Planner | Dependency-aware execution plan from tool catalogue + knowledge | `execution_plan`, per-agent instruction blocks |
| Programmer | Code generation for custom tools and scripts | New `@tool` functions added at runtime |
| Preprocessing | Interpret preprocessing instructions; select tools | Ordered tool call sequence |
| SimSetup | Interpret setup instructions; resolve naming mismatches | Ordered tool call sequence |
| HPC | Interpret HPC instructions; estimate resources | SLURM script parameters |
| Analysis | Select analysis metrics from goal; order tool calls | Observable suite and plot parameters |
| Reporter | Literature narrative synthesis; results discussion | HTML narrative, final impression |

**Interactive replanning (human-in-the-loop):** modification requests (e.g. "extend to 25 ns, use CHARMM36") trigger sentinel-based replanning (`PLAN_UPDATE:<agent_key>`) combined with regex parameter patching of tool dictionaries — providing semantically flexible yet numerically precise updates.

**Graceful degradation:** every LLM-dependent operation activates a deterministic fallback (heuristic routing, template plans, rule-based report synthesis) when the server is unreachable. A mock mode supports offline unit testing.

---

## 2.4 Structure Acquisition and Domain Intelligence

A key extension beyond PDB-only workflows is **on-demand structure acquisition** from public databases, enabling studies that begin from a UniProt accession alone.

### 2.4.1 Structure download pipeline

```
  User goal: "UniProt P21860, kinase domain"
          |
          v
  structure_request_parser
  (extract UniProt ID, domain label, residue range)
          |
          v
  Local PDB exists? ──YES──> use existing file
          |
         NO
          |
          v
  structure_sources registry
  ┌───────────────────┬────────────────────┐
  │  AlphaFold API    │   RCSB PDB         │
  │  (default)        │   (fallback)       │
  └─────────┬─────────┴──────────┬─────────┘
            └──────────┬─────────┘
                       v
             Full-length PDB downloaded
                       |
                       v
          Domain / residue range specified?
          ├──NO──> pass full PDB directly
          |
         YES
          |
          v
  domain_sources  (UniProt REST API)
  → annotated boundary: residues 709–966
          |
          v
  extract_domain  (BioPython / MDAnalysis)
  → ERBB3_kinase_domain.pdb  (258 residues)
          |
          v
  structure_validator
  (missing residues, broken backbone Ca-Ca > 4.5 A)
          |
          v
  Preprocessing agent  (cleaned_pdb -> simsetup)
```

| Module | Path | Function |
|--------|------|----------|
| Request parser | `src/preprocess/structure_request_parser.py` | Extracts UniProt ID, domain labels, residue ranges; scopes analysis-only ranges separately from simulation domain |
| Structure sources | `src/preprocess/structure_sources/` | Pluggable download backends (AlphaFold, RCSB) |
| Domain sources | `src/preprocess/domain_sources/` | UniProt feature lookup (Domain/Region annotations) with offline fallback |
| Domain extractor | `src/preprocess/domain_extractor.py` | Trims PDB to requested residue span |
| Acquisition tool | `src/preprocess/acquire_structure_tool.py` | End-to-end download → extract → validate for the preprocessing agent |

Structure validation (`structure_validator.py`) reports missing residues, broken backbone geometry (Cα–Cα > 4.5 Å), and component availability before simulation setup proceeds.

---

## 2.5 Multi-Simulation Mode and Component-Case Expansion

AgenticAI supports batch execution from a single CLI invocation. Simulations are spawned when the user supplies multiple PDB files (`--pdb-list`), mentions multiple PDBs in the goal, or requests **multiple component cases from one structure** (e.g. protein-only and protein+ATP+MG from the same AlphaFold model).

### 2.5.1 Orchestration model

```
  run_agenticAIWork.py  --simtype multisim
          |
          v
  Supervisor: build master plan
  ┌─────────────────────────────────────────────┐
  │  master_plan.md                              │
  │  sim_prompts = [                             │
  │    {label: p21860,         case: apo},       │
  │    {label: p21860_ATP_MG,  case: holo},      │
  │  ]                                           │
  └───────────────┬─────────────────────────────┘
                  │
        ┌─────────┴──────────┐
        │                    │
        v                    v
  Sim 1: p21860          Sim 2: p21860_ATP_MG
  (protein only)         (protein + ATP + MG)
  preprocess             feasibility check
  simsetup                    │
  hpcjob              FAIL: ligand/ion absent
  save completed_sim_state    │
        │               SKIP + record reason
        │                    │
        └──────────┬─────────┘
                   │
                   v
        Combined Analysis  (base_dir/analysis/)
        ┌──────────────────────────────────────┐
        │  overlay plots (RMSD, RMSF, Rg, ...)  │
        │  DCCM panels + DCCM difference        │
        │  segment RMSF bars (resid 150-190)    │
        │  COM pocket distance overlay          │
        │  statistical_summary.json             │
        └──────────────────┬───────────────────┘
                           │
                           v
        Combined Reporter  (reporter/combined_report.html)
        + run_summary.md / run_summary.json   (base dir)
```

| Concept | Definition | Example |
|---------|------------|---------|
| Source PDB | One downloaded or user-supplied structure | `p21860.pdb` (AlphaFold, full ERBB3) |
| Component case | Simulation system composition | `protein only` vs `protein + ATP + MG` |
| Simulation label | Directory name / legend label | `p21860`, `p21860_ATP_MG` |
| Total simulations | `len(sim_prompts)`, not `len(pdb_list)` | 1 PDB × 2 cases = **2 simulations** |

Each simulation receives an isolated working directory (`base_dir/{label}/`). Per-simulation goals are rewritten to reference only the local structure while preserving shared parameters. The Supervisor loops sequentially through `sim_prompts`, saving `completed_sim_states` snapshots (success, skipped, job_id, errors).

### 2.5.2 Combined analysis phase

After all per-simulation pipelines complete (or are skipped with recorded reasons), combined analysis at `base_dir/analysis/` and `base_dir/combinedAnalysis/` includes:

1. **Comparative overlay plots** (RMSD, RMSF, Rg, energy, COM distance).
2. **Segment RMSF overlays** for user-defined residue windows.
3. **DCCM panels** and **apo–holo DCCM difference** heatmaps.
4. **Statistical summary** (`statistical_summary.json`): mean, std, min, max per metric.
5. **Cross-simulation PCA** (optional; scikit-learn on Cα coordinates).
6. **Combined HTML report** (`reporter/combined_report.html`) with literature-correlated discussion.

---

## 2.6 Human-in-the-Loop Checkpoints

Optional approval gates after preprocessing, simulation setup, and HPC completion. User feedback is normalised via fuzzy phrase matching (`approved`, `retry`, `reject`); retry requests trigger parameter extraction and plan patching before re-execution.

---

## 2.7 Implementation and Availability

| Component | Version / detail |
|-----------|------------------|
| Python | 3.11 |
| LangGraph / LangChain | 1.0.7 / 1.2.8 |
| GROMACS | 2025.4 |
| AmberTools | 24.8 |
| MDAnalysis | 2.10.0 |
| scikit-learn | 1.6.1 (cross-sim PCA) |
| Ollama | 0.6.1 (local LLM) |

**CLI entry point:** `run_agenticAIWork.py`

```bash
python run_agenticAIWork.py \
  --goal "<natural-language MD objective>" \
  --working-dir <project_dir> \
  --subtask preprocess simsetup hpcjob analysis reporter \
  --simtype multisim \
  --use-llm --no-human-loop
```

**Subtask modes** allow isolated pipeline stages: `preprocess`, `simsetup`, `hpcjob`, `analysis`, `reporter`.

Source code: [GitHub repository URL — insert before submission].

---

## Figure and Table Inventory for Methods (manuscript preparation)

| Manuscript figure | Suggested source | Status |
|-------------------|------------------|--------|
| Fig. 1 — System architecture | Section 2.1.1 ASCII diagram → redraw as vector graphic for submission | **Draft ready** |
| Fig. 2 — Structure acquisition flow | Section 2.4.1 ASCII diagram | **Draft ready** |
| Fig. 3 — Multi-sim orchestration | Section 2.5.1 ASCII diagram | **Draft ready** |
| Table 1 — Modularity properties | Section 2.1 table | **Draft ready** |
| Table 2 — Agent inference layers | Section 2.2.4 table | **Draft ready** |
| Table 3 — Analysis tool suite | Section 2.4.4 table | **Draft ready** |
| Supp. Fig. S1 — Log snapshot (Planner plan) | `planner/master_plan.md` or `agent_conversation.log` | **Insert screenshot** |
| Supp. Fig. S2 — Run summary | `run_summary.md` | **Insert screenshot** |
