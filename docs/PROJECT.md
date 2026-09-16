# AgenticAI — LLM-Powered Molecular Dynamics Workflow

**This file is the project overview.** Start here to learn what AgenticAI
does, which features it ships, how the repository is laid out, how to run a
job, and which files a run writes. It is not the design of the LangGraph, the
analysis-tool theory, or the coding rules — those live in the other `docs/`
pages listed under [Documentation](#documentation).

---

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
6. Analyses the resulting trajectory (RMSD, RMSF, Rg, DCCM, DSSP, COM distances,
   plus optional family-scale modular dynamics)
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
- **Multi-replicate MD** — `--rep-num N` fans analysis across `hpc/repXX/` and
  writes mean±std under `analysis/avg/` for overlays and classification.
- **Holo feasibility guard** — if a requested ligand/ion is absent in the source
  structure (e.g. AlphaFold has no ATP), the Supervisor skips the holo case and
  records the reason rather than producing a broken simulation.
- **Supervisor-Planner-Programmer-Agent hierarchy** — a supervisor validates
  feasibility and routes; a planner builds an execution plan from a live tool
  catalogue; field agents carry out each step.
- **LLM-driven scientific inference** — the Planner selects analysis observables
  from goal semantics; the Analysis agent selects tools per trajectory; the
  Reporter synthesises a literature-grounded narrative.
- **Family modular dynamics** — consensus-mapped torsions, RMSF, N↔C DCCM, and
  independent dihedral PCA landscape entropy when the goal asks for comparative
  kinase/pseudokinase descriptors (not a fixed paper schema).
- **Consensus reference pocket** — define ATP pocket on a reference (e.g. KAPCA),
  map via star MSA, compute COM distance + axis orientation for all systems.
- **LLM classification feature selection** — after collecting dynamics scalars,
  the Analysis agent asks the LLM to choose a scientifically motivated subset
  (with written reasoning) before hierarchical clustering / dendrogram+heatmap.
- **Human checkpoints** — optional approval gates after preprocessing, setup, HPC,
  analysis, and reporter. Enable with `--HITL all` or pause on failures with `--HITL error`.
- **Cross-sim HPC pool** — multi-sim full pipeline preps in parallel (local
  workers), submits up to N SLURM jobs in parallel, then runs post-HPC
  analysis/reporter (see [POOLS.md](POOLS.md)).
- **Graceful LLM fallback** — deterministic heuristic routing when LLM unavailable.
- **Run audit trail** — `agent_conversation.log`, `execution_plan.md`,
  `execution_report.md`, `run_summary.md`, and `run_summary.json` at the
  base working directory after every run.
- **Interactive HTML report** — literature (PubMed + bioRxiv + UniProt),
  analysis plots, DCCM and DCCM-difference heatmaps, and a 3Dmol.js viewer
  with trajectory snapshots and PNG export.

## Repository Layout

```
SimAgent.py            # CLI entry point
environment.yml                 # Conda environment (ollama_env, Python 3.11)
agentic/
    state.py                    # MDState TypedDict — central shared state (~65 fields)
    workflow.py                 # LangGraph StateGraph (12 nodes)
    supervisor/                 # MDSupervisor: routing, enrichment, multi-sim loop
    planner/                    # MDPlanner + MDProgrammer; knowledge/ knowledge base
    preprocess/                 # PreprocessingAgent: download, domain trim, clean
    simsetup/                   # SimulationSetupAgent: topology, MDP, solvation
    hpc/                        # MDHPCAgent: SLURM, SSH, job monitoring
    analysis/                   # MDAnalysisAgent: traj metrics, modular family tools,
                                #   combined overlays, LLM feature selection + clustering
    reporter/                   # ReporterAgent: HTML report, literature, 3D viewer
    utils/                      # Logging, SecureFileManager, plan persistence
    multi_sim_progress.py       # Per-sim / family-modular completion checks
src/
    analysis/                   # Trajectory tools, classification collector/clustering,
                                #   consensus pocket, family_dynamics_core, replicate avg
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

## Documentation

| Doc | What it covers |
|-----|----------------|
| [PROJECT.md](PROJECT.md) | This page — product overview, layout, quick start, CLI, run outputs |
| [PIPELINE_WORKFLOW.md](PIPELINE_WORKFLOW.md) | Agent order, directories, files, and flag examples |
| [ARCHITECTURE.md](ARCHITECTURE.md) | LangGraph, shared state, agents, directory layout |
| [CONVENTIONS.md](CONVENTIONS.md) | Coding and documentation rules for contributors |
| [ANALYSIS_TOOLS.md](ANALYSIS_TOOLS.md) | Per-tool observables, theory, and output filenames |
| [TOOLS.md](TOOLS.md) | External dependencies plus GROMACS/analysis mechanisms |
| [POOLS.md](POOLS.md) | Local parallel workers and SLURM HPC pool |
| [OLLAMA_SETUP.md](OLLAMA_SETUP.md) | Ollama server + `gpt-oss:20b` (separate from conda) |

Each page opens with a purpose paragraph. Related mechanisms share one
descriptive file (tools together, pools together). Do not leave the
explanation only in chat or code comments. Full CLI flags:
[README.md](../README.md).

## Quick Start

```bash
# 1. Create the environment
conda env create -f environment.yml
conda activate ollama_env

# 2. Basic run from a local PDB (LLM on by default, no HITL)
python SimAgent.py \
    --goal "Run MD simulation of my_protein.pdb" \
    --working-dir /work/run1

# 3. From a UniProt accession (downloads AlphaFold, extracts domain)
python SimAgent.py \
    --goal "Study ATP binding dynamics of UniProt P21860 ERBB3 kinase domain" \
    --working-dir /work/erbb3 \
    --subtask preprocess simsetup hpcjob

# 4. Custom LLM endpoint (Ollama must be running)
python SimAgent.py \
    --goal "Simulate the kinase-ligand complex" \
    --llm-base-url http://localhost:11434

# 5. Multi-protein comparative study (explicit PDB list)
python SimAgent.py \
    --goal "Compare pseudokinase dynamics for p21860, q8iv63 — apo and ATP-bound" \
    --pdb-list p21860.pdb q8iv63.pdb \
    --working-dir /work/pseudo \
    --subtask preprocess simsetup hpcjob

# 6. Interactive checkpoints
python SimAgent.py \
    --goal "..." \
    --working-dir /work/run1 \
    --HITL all

# 7. Subtask mode (run only specific agents)
python SimAgent.py \
    --subtask analysis reporter \
    --goal "Analyse existing trajectory in /work/run1/hpc" \
    --working-dir /work/run1
```

## CLI Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--goal` | *(required)* | Natural-language simulation goal |
| `--working-dir` | `.` | Campaign base; each sim writes under `{dir}/{label}/` |
| `--pdb-list` | *(none)* | Explicit PDB file list for multi-sim |
| `--sim-dirs` | *(none)* | Existing sim dirs for analysis-only multi-sim |
| `--subtask` | *(all)* | Agents to run: `preprocess simsetup hpcjob analysis reporter` |
| `--no-llm` | `False` | Disable LLM-powered routing and planning |
| `--llm-model` | `gpt-oss:20b` | Ollama model name |
| `--llm-base-url` | `http://127.0.0.1:11434` | Ollama server URL |
| `--HITL` | off | `error` or `all` — enable human-in-the-loop |
| `--resume` | off | Restore `{working-dir}/supervisor/state.jsonl` and continue |
| `--combined-only` | off | Combined analysis + reporter only (existing per-sim results) |
| `--allowed-hpc-jobs` | auto | Max concurrent SLURM jobs in cross-sim HPC pool |
| `--hpc-check-interval` | `2h` | SLURM poll interval during HPC pool wait |
| `--llm-concurrency` | auto | Cap on concurrent LLM-using workers (prep / analysis) |
| `--force-field` | `amber99sb-ildn` | GROMACS force field override |
| `--water-model` | `tip3p` | Water model override |
| `--rep-num` | `1` | Independent production replicates per system (`hpc/repXX/`) |
| `--prompt` | *(none)* | Override enriched prompt |
| `--log-file` | *(auto)* | Conversation log path |

This is the common subset. Parallel-pool and remaining flags:
[POOLS.md](POOLS.md) and [README.md](../README.md).

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
| `analysis/classification_features*.csv` | Raw + robust z-score feature matrix (when classified) |
| `analysis/classification_feature_selection.json` | LLM-chosen columns + scientific reasoning |
| `analysis/classification_dendrogram_heatmap.png` | Ward dendrogram + feature heatmap panel |
| `cross_sim/` | Pre-combined MSA / pocket-map artifacts (multi-sim) |
