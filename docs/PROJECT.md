# AgenticAI — LLM-Powered Molecular Dynamics Workflow

## Overview

AgenticAI is an agentic AI system that automates molecular dynamics (MD) simulation
workflows using LLM-powered reasoning, intelligent task orchestration, and optional
human-in-the-loop decision making.

Given a natural-language goal and either a PDB file or a UniProt accession, the system:

1. Resolves the protein structure — downloads from AlphaFold or RCSB if no local file
2. Extracts a specific domain if requested (e.g. "kinase domain"), using UniProt
   residue annotations
3. Validates and preprocesses the structure (protonation, component separation)
4. Generates simulation parameters, topology, and coordinates (GROMACS)
5. Submits and monitors HPC jobs via SLURM
6. Analyses the resulting trajectory (RMSD, RMSF, Rg, DCCM, DSSP, COM distances)
7. Produces an interactive HTML report with literature references, figures, and a
   3D structure viewer

## Key Features

- **Natural-language interface** — describe what you want; the LLM translates it
  into a concrete, dependency-aware MD plan.
- **UniProt / AlphaFold integration** — start from a UniProt accession alone; the
  framework downloads the predicted structure and extracts the requested domain.
- **Domain intelligence** — named domains (e.g. "kinase domain") are resolved to
  exact residue ranges via the UniProt REST API, not hard-coded numbers.
- **Multi-simulation and component-case expansion** — a single command can drive
  N proteins × M component cases (e.g. apo + holo) with isolated per-sim
  directories and a combined analysis phase.
- **Holo feasibility guard** — if a requested ligand/ion is absent in the source
  structure (e.g. AlphaFold has no ATP), the Supervisor skips the holo case and
  records the reason rather than producing a broken simulation.
- **Supervisor-Planner-Programmer-Agent hierarchy** — a supervisor validates
  feasibility and routes; a planner builds an execution plan from a live tool
  catalogue; field agents carry out each step.
- **LLM-driven scientific inference** — the Planner selects analysis observables
  from goal semantics; the Analysis agent selects tools per trajectory; the
  Reporter synthesises a literature-grounded narrative.
- **Human checkpoints** — optional approval gates after preprocessing, setup, HPC,
  analysis, and reporter. Enable with `--HITL all` or pause on failures with `--HITL error`.
- **Cross-sim HPC pool** — multi-sim full pipeline preps sequentially, submits up to N
  SLURM jobs in parallel, then runs post-HPC analysis/reporter (see `docs/HPC_POOL.md`).
- **Graceful LLM fallback** — deterministic heuristic routing when LLM unavailable.
- **Run audit trail** — `agent_conversation.log`, `execution_plan.md`,
  `execution_report.md`, `run_summary.md`, and `run_summary.json` at the
  base working directory after every run.
- **Interactive HTML report** — literature (PubMed + bioRxiv + UniProt),
  analysis plots, DCCM and DCCM-difference heatmaps, and a 3Dmol.js viewer
  with trajectory snapshots and PNG export.

## Repository Layout

```
run_agenticAIWork.py            # CLI entry point
environment.yml                 # Conda environment (ollama_env, Python 3.11)
agentic/
    state.py                    # MDState TypedDict — central shared state (~65 fields)
    workflow.py                 # LangGraph StateGraph (12 nodes)
    supervisor/                 # MDSupervisor: routing, enrichment, multi-sim loop
    planner/                    # MDPlanner + MDProgrammer; knowledge/ knowledge base
    preprocess/                 # PreprocessingAgent: download, domain trim, clean
    simsetup/                   # SimulationSetupAgent: topology, MDP, solvation
    hpc/                        # MDHPCAgent: SLURM, SSH, job monitoring
    analysis/                   # MDAnalysisAgent: RMSD/RMSF/DCCM/combined overlays
    reporter/                   # ReporterAgent: HTML report, literature, 3D viewer
    utils/                      # Logging, SecureFileManager, plan persistence
src/
    preprocess/
        structure_sources/      # AlphaFold + RCSB download backends (pluggable)
        domain_sources/         # UniProt domain lookup + offline fallback
        structure_request_parser.py
        domain_extractor.py
        structure_downloader.py
        acquire_structure_tool.py
        domain_lookup_tool.py
        structure_validator.py
        complex_separator.py
        hydrogen_adder.py
    supervisor/
        input_validator.py      # Goal parsing, UniProt resolution, feasibility
        unified_enricher.py     # Single LLM enrichment call
        component_parser.py     # Holo component validation
    reporter/
        combined_reporter.py    # Cross-simulation HTML report generation
    utils/
        run_summary.py          # Build + write run_summary.md / run_summary.json
        pdb_analyzer.py
        chat_tools.py
docs/                           # Project documentation (you are here)
```

## Quick Start

```bash
# 1. Create the environment
conda env create -f environment.yml
conda activate ollama_env

# 2. Basic run from a local PDB (LLM on by default, no HITL)
python run_agenticAIWork.py \
    --goal "Run MD simulation of my_protein.pdb" \
    --working-dir /work/run1

# 3. From a UniProt accession (downloads AlphaFold, extracts domain)
python run_agenticAIWork.py \
    --goal "Study ATP binding dynamics of UniProt P21860 ERBB3 kinase domain" \
    --working-dir /work/erbb3 \
    --subtask preprocess simsetup hpcjob \
    --simtype multisim

# 4. Custom LLM endpoint (Ollama must be running)
python run_agenticAIWork.py \
    --goal "Simulate the kinase-ligand complex" \
    --llm-base-url http://localhost:11434

# 5. Multi-protein comparative study (explicit PDB list)
python run_agenticAIWork.py \
    --goal "Compare pseudokinase dynamics for p21860, q8iv63 — apo and ATP-bound" \
    --pdb-list p21860.pdb q8iv63.pdb \
    --working-dir /work/pseudo \
    --subtask preprocess simsetup hpcjob \
    --simtype multisim

# 6. Interactive checkpoints
python run_agenticAIWork.py \
    --goal "..." \
    --working-dir /work/run1 \
    --HITL all

# 7. Subtask mode (run only specific agents)
python run_agenticAIWork.py \
    --subtask analysis reporter \
    --goal "Analyse existing trajectory in /work/run1/hpc" \
    --working-dir /work/run1
```

## CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--goal` | *(required)* | Natural-language simulation goal |
| `--working-dir` | `working_dir/` | Base output directory |
| `--simtype` | `singlesim` | `singlesim` or `multisim` |
| `--pdb-list` | *(none)* | Explicit PDB file list for multi-sim |
| `--sim-dirs` | *(none)* | Existing sim dirs for analysis-only multi-sim |
| `--subtask` | *(all)* | Agents to run: `preprocess simsetup hpcjob analysis reporter` |
| `--no-llm` | `False` | Disable LLM-powered routing and planning |
| `--llm-model` | `gpt-oss:20b` | Ollama model name |
| `--llm-base-url` | `http://127.0.0.1:11434` | Ollama server URL |
| `--HITL` | off | `error` or `all` — enable human-in-the-loop |
| `--allowed-hpc-jobs` | `5` | Max concurrent SLURM jobs in cross-sim HPC pool |
| `--hpc-check-interval` | `2h` | SLURM poll interval during HPC pool wait |
| `--force-field` | `amber99sb-ildn` | GROMACS force field override |
| `--water-model` | `tip3p` | Water model override |
| `--prompt` | *(none)* | Override enriched prompt |
| `--log-file` | *(auto)* | Conversation log path |

## Run Outputs

After every run the following are written to the base working directory:

| File | Description |
|------|-------------|
| `run_summary.md` | Human-readable run outcome: mode, counts, per-sim status, domain context |
| `run_summary.json` | Same data in structured JSON for scripts |
| `agent_conversation.log` | Full agent dialogue, LLM prompts/responses, routing decisions |
| `planner/master_plan.md` | Multi-sim master plan with per-case prompts and combined analysis plan |
| `supervisor/execution_report.md` | Stage-by-stage execution summary |
| `reporter/combined_report.html` | Interactive HTML report (multi-sim) |
| `analysis/statistical_summary.json` | Cross-simulation statistics table |
