# AgenticAI Tutorial — End-to-End Usage Guide

This guide walks you from installation through common workflows: single and
multi-simulation studies, analysis-only reruns, combined reporting, and
troubleshooting. For a short overview, see [README.md](README.md).

---

## Table of contents

1. [How a run works](#1-how-a-run-works)
2. [Prerequisites](#2-prerequisites)
3. [Core CLI flags](#3-core-cli-flags)
4. [Workflow recipes](#4-workflow-recipes) (including [HPC pool](#48-full-multi-sim-pipeline-with-hpc-pool) and [family modular](#49-family-modular-comparative-dynamics--classification))
5. [Artifacts — what gets produced](#5-artifacts--what-gets-produced)
6. [Simulation parameters](#6-simulation-parameters)
7. [LLM setup](#7-llm-setup)
8. [Resume and retry](#8-resume-and-retry)
8.1. [Unsupervised classification](#81-unsupervised-classification-multi-simulation)
9. [Reading run outputs](#9-reading-run-outputs)
10. [Troubleshooting](#10-troubleshooting)
11. [Best practices](#11-best-practices)

---

## 1. How a run works

Every invocation follows the same high-level path:

```
Your --goal  →  Supervisor  →  Planner  →  Field agents  →  Summary + reports
```

| Stage | Agent(s) | What happens |
|-------|----------|--------------|
| **Validation** | Supervisor | Parses goal, PDBs, UniProt IDs, simulation mode |
| **Planning** | Planner | Builds an execution plan and tool calls |
| **Preprocess** | Preprocessing | Clean PDB, separate components, domain trim |
| **Sim setup** | SimSetup | Topology, solvation, ions, MDP files |
| **HPC** | HPC | SLURM script, submit, monitor |
| **Analysis** | Analysis | Traj metrics; optional modular family tools; combined overlays + classification |
| **Report** | Reporter | HTML report + literature |

Use `--subtask` to run only the stages you need (e.g. `analysis reporter` on
finished trajectories). Every campaign uses `{base}/{label}/` directories.
When `len(sim_prompts) > 1`, the supervisor also runs **combined analysis**
and a **combined HTML report** at the base `--working-dir`.

Stage order for multi-sim (`n_sims > 1`):

1. Optional **`pre_combined`** — MSA / consensus pocket → `{base}/cross_sim/`
2. Per-sim analysis → reporter (with `--rep-num N`, fan-out to `analysis/avg/`)
3. Optional **`post_combined`** — overlays; if classification requested: collect
   features → LLM feature selection → Ward dendrogram+heatmap
4. **`combined_reporter`** when post ran

When the full pipeline runs (preprocess through reporter), the **HPC pool**
uses three explicit stages:

1. **Prep all** — preprocess + simsetup for every case (local workers).
2. **HPC pool** — submit and monitor up to `--allowed-hpc-jobs` SLURM jobs in parallel.
3. **Post-HPC all** — per-sim analysis + reporter, then combined outputs at `{base}/` when N>1.

**Human checkpoints** are optional. By default the workflow is fully automatic.
Use `--HITL error` to pause only on failures, or `--HITL all` for every checkpoint.

---

## 2. Prerequisites

```bash
conda env create -f environment.yml
conda activate ollama_env
```

Optional: confirm your LLM endpoint is reachable (LLM is **on by default**):

```bash
curl -s http://127.0.0.1:11434/api/tags
```

Use `--no-llm` only for offline or deterministic fallback runs.

GROMACS is included in the conda environment. For phosphorylated proteins with
CHARMM36, install `charmm36-jul2022.ff` separately (see README **Force Fields**).

---

## 3. Core CLI flags

```bash
python SimAgent.py --goal "..." [options]
```

| Flag | Description |
|------|-------------|
| `--goal` | Natural-language task (**required**) |
| `--working-dir` | Campaign base; each sim under `{dir}/{label}/` |
| `--subtask` | Agents to run: `preprocess simsetup hpcjob analysis reporter` |
| `--pdb-list` | Explicit PDB list |
| `--sim-dirs` | Existing per-sim directories (analysis-only) |
| `--no-llm` | Disable LLM planning (deterministic fallback) |
| `--llm-model` | Model name (default `gpt-oss:20b`) |
| `--llm-base-url` | Endpoint URL (default `http://localhost:11434`) |
| `--HITL` | `error` or `all` — enable human-in-the-loop (default: off) |
| `--force-field` | Override force field (default `amber99sb-ildn`) |
| `--water-model` | Override water model (default `tip3p`) |
| `--allowed-hpc-jobs` | Max concurrent SLURM jobs in cross-sim HPC pool (default `5`) |
| `--rep-num` | Independent production replicates per label (default `1`; nested `hpc/repXX` + `analysis/avg/`) |
| `--hpc-check-interval` | Poll interval during HPC pool wait (default `2h`) |
| `--resume` | Multi-sim: skip succeeded sims, retry failures |
| `--retry-labels` | Force-retry specific simulation labels |
| `--combined-only` | Multi-sim: skip per-sim loop; run combined analysis + report only |

---

## 4. Workflow recipes

Choose the path that matches your starting point.

### 4.1 Single simulation from a local PDB

Full pipeline through HPC submission:

```bash
python SimAgent.py \
  --goal "Preprocess and setup MD for my_protein.pdb for 50 ns, then submit to HPC" \
  --working-dir /work/s1 \
  --subtask preprocess simsetup hpcjob
```

### 4.2 UniProt accession (no local PDB)

The framework can download from AlphaFold (default) or RCSB and extract a domain
via UniProt:

```bash
python SimAgent.py \
  --goal "Study ATP binding dynamics of UniProt P21860 (ERBB3).
          Download the AlphaFold PDB, extract the kinase domain,
          and run 1 ns MD for two cases: 1. Protein only, 2. Protein + ATP + MG.
          Submit both jobs to HPC." \
  --working-dir /work/erbb3 \
  --subtask preprocess simsetup hpcjob
```

**Domain by name or residue range:**

```bash
# By name (resolved via UniProt):
--goal "...kinase domain of P21860..."

# By residue range (no API call):
--goal "...simulate residues 709-966 of P21860..."
```

**Holo feasibility guard:** If the source is AlphaFold and the goal requests
ATP+MG, the holo case is **skipped automatically** when ligands are absent.
The skip reason appears in `run_summary.md`.

### 4.3 Multi-protein study (several PDBs)

```bash
python SimAgent.py \
  --goal "Run 100 ns MD for each pseudokinase and submit to HPC.
          Names: p21860=ERBB3, q8iv63=VRK3, q8nb16=MLKL, q8wz42=TITIN." \
  --pdb-list p21860.pdb q8iv63.pdb q8nb16.pdb q8wz42.pdb \
  --working-dir /work/pseudo \
  --subtask preprocess simsetup hpcjob
```

### 4.4 Component-case expansion (apo vs holo from same PDB)

Use explicit phrasing — *"two different cases"*, *"1. Protein only"*,
*"2. Protein + ATP + MG"*:

```bash
python SimAgent.py \
  --goal "Study ATP binding for p21860.pdb, q8iv63.pdb, q8nb16.pdb.
          For each PDB run two cases: 1. Protein only, 2. Protein + ATP + MG.
          Total 6 simulations. Preprocess, setup, and submit to HPC." \
  --working-dir /work/pseudo \
  --subtask preprocess simsetup hpcjob
```

Expected layout: `p21860/`, `p21860_ATP_MG/`, `q8iv63/`, `q8iv63_ATP_MG/`, …

### 4.5 Per-simulation analysis + report (trajectories already finished)

**Single simulation:**

```bash
python SimAgent.py \
  --goal "Simulation is complete in /work/s1/hpc. Compute RMSD, RMSF, Rg,
          DCCM, DSSP, and generate the report." \
  --working-dir /work/s1 \
  --subtask analysis reporter
```

**Multi-simulation** (full per-sim loop, then combined report):

```bash
python SimAgent.py \
  --goal "Analyse all completed pseudokinase simulations. Compute RMSD, RMSF, Rg,
          DCCM apo vs holo difference, RMSF for activation loop residues 150-200,
          ATP pocket COM distance, and DSSP for the activation loop.
          Generate combined comparison report with literature." \
  --working-dir /work/pseudo \
  --subtask analysis reporter
```

**Analysis from existing directories** (`--sim-dirs`):

```bash
python SimAgent.py \
  --goal "Compare structural dynamics across completed simulations." \
  --sim-dirs /work/pseudo/p21860 /work/pseudo/p21860_ATP_MG \
  --working-dir /work/pseudo \
  --subtask analysis reporter
```

### 4.6 Combined analysis + report only (`--combined-only`)

When **every simulation already has** `analysis/analysis_summary.jsonl`, skip
the per-sim loop and jump straight to cross-simulation overlays and the HTML report:

```bash
python SimAgent.py \
  --goal "Generate combined comparison plots and multi-simulation report
          for completed pseudokinase runs (ERBB3, VRK3, MLKL, TITIN)." \
  --working-dir /work/pseudo \
  --subtask analysis reporter \
  --combined-only
```

The supervisor discovers simulations from existing `analysis_summary.jsonl`
files and writes combined outputs under `{working-dir}/analysis/` and
`{working-dir}/reporter/combined_report.html`.

### 4.7 Subtask shortcuts

| Goal | `--subtask` |
|------|-------------|
| Preprocess only | `preprocess` |
| Setup + HPC (preprocess done) | `simsetup hpcjob` |
| Analysis + report | `analysis reporter` |
| Full pipeline | omit (all agents) |

### 4.8 Full multi-sim pipeline with HPC pool

When you omit `--subtask`, the supervisor runs preprocess → simsetup → HPC →
analysis → reporter for every simulation, using the **cross-sim HPC pool**:

1. **Prep (local workers)** — preprocess + simsetup in parallel when HITL is off.
2. **HPC pool (parallel)** — up to `--allowed-hpc-jobs` SLURM jobs run at once.
3. **Poll** — the workflow sleeps and re-checks SLURM every `--hpc-check-interval`.
4. **Post-HPC (local workers)** — per-sim analysis and reporter, then combined analysis + report.

Directory trees and more flag examples: [docs/PIPELINE_WORKFLOW.md](docs/PIPELINE_WORKFLOW.md).

```bash
python SimAgent.py \
  --goal "Run 1 ns MD for p23458 (JAK1), p29597 (TYK2), q7rtn6 (STRAA).
          Compare RMSF and ligand pocket distance across simulations.
          DCCM for JAK1 and TYK2 only." \
  --working-dir ./my_study \
  --allowed-hpc-jobs 4 \
  --hpc-check-interval 3m
```

If the process is interrupted during HPC, restart with the same `--working-dir`
and `--resume`. Pool state in `supervisor/state.jsonl` restores job IDs and prep
status. See [docs/POOLS.md](docs/POOLS.md).

Use `--HITL error` to pause on SLURM submit failures or terminal job states;
use `--HITL all` to review after every stage.

### 4.9 Family modular comparative dynamics (+ classification)

For kinase/pseudokinase panels, describe **scientific descriptors** in the goal
(not internal CSV column names). The planner schedules consensus tools; after
collecting the feature table, the analysis agent asks the LLM to select a
subset with written reasoning, then builds a dendrogram+heatmap.

```bash
python SimAgent.py \
  --goal "Protein–ATP holo systems under this working directory. Use KAPCA
          (p17612) as the reference to define the ATP pocket (15 Å of ATP),
          map with a global MSA. From both replicates (then average): ATP–pocket
          COM distance mean/std, pocket axis orientation mean/std, consensus Cα
          RMSF mean/std, pocket χ₁ circular mean, N↔C DCCM, independent
          dihedral PCA landscape entropy. Hierarchical clustering dendrogram
          with feature heatmap; do not fix k. Combined HTML report." \
  --working-dir ./pseudokin_5x2/run_01 \
  --rep-num 2 \
  --subtask analysis reporter \
  --combined-only
```

Details: [docs/ANALYSIS_TOOLS.md](docs/ANALYSIS_TOOLS.md#modular-family-dynamics-torsions--pca--tica)
and [§8.1](#81-unsupervised-classification-multi-simulation).

---

## 5. Artifacts — what gets produced

An **artifact** is any file or structured output the pipeline writes to disk:
structures, topologies, trajectories, plots, logs, plans, and reports. Artifacts
are the durable record of a run — use them to resume work, audit decisions, or
feed downstream analysis.

### 5.1 Base working directory (`--working-dir`)

| Artifact | Purpose |
|----------|---------|
| `run_summary.md` | Human-readable outcome: counts, job IDs, skip reasons |
| `run_summary.json` | Same data in machine-readable form |
| `agent_conversation.log` | Full audit trail (routing, LLM calls, tool results) |
| `supervisor/state.jsonl` | Checkpoint for resume / combined-only routing |
| `analysis/` | **Combined** overlays, DCCM panels; `classification_*` when requested |
| `cross_sim/` | Optional pre_combined MSA / pocket-map artifacts |
| `reporter/combined_report.html` | Multi-simulation HTML report (multi-sim only) |
| `planner/master_plan.md` | Cross-simulation plan and per-case prompts |

### 5.2 Per-simulation directory (`{working-dir}/{label}/`)

Each simulation (e.g. `p21860/`, `p21860_ATP_MG/`) is isolated:

```
{label}/
  preprocess/     # cleaned PDB, protonated structures, component splits
  simsetup/       # topol.top, *.gro, *.mdp
  hpc/            # SLURM script, *.xtc (or hpc/rep01, rep02 with --rep-num)
  analysis/       # per-sim plots; optional consensus_*/ and avg/
  reporter/       # per-sim report.html
  planner/        # execution_plan.md
  supervisor/     # per-sim state checkpoint
  agent_conversation.log
```

**Key analysis artifacts** (under `{label}/analysis/`):

- `analysis_summary.jsonl` — structured record of every analysis step (required for `--combined-only`)
- `rmsd.png`, `rmsf.png`, `rg.png`, `dccm_heatmap.png`
- `dssp_raw_data.dat`, `dssp_heatmap.png` (when DSSP was run)
- `avg/` — multi-rep mean±std products when `--rep-num N`
- `consensus_dihedrals/`, `consensus_rmsf/`, `consensus_DCCM/`, `consensus_PCA/` — family modular outputs

**Key combined artifacts** (under `{working-dir}/analysis/`):

- `rmsd_overlay.png`, `rmsf_apo_holo_*.png`, `dccm_apo_holo_*_panels.png`
- `dssp_comparison.png` — helix/sheet/coil bar chart across all sims
- `classification_features.csv` / `_zscore.csv` — when classification requested
- `classification_feature_selection.json` — LLM-chosen columns + reasoning
- `classification_dendrogram_heatmap.png` — dendrogram + feature heatmap
- `dssp_activation_loop_*.png` — activation-loop DSSP heatmaps (residues 150–200 by default)

Artifacts are referenced in `run_summary.md` and embedded in HTML reports.
If a simulation is missing an artifact (e.g. DSSP for one apo run), combined
analysis can **backfill** DSSP from trajectory files when trajectories exist in
`hpc/`.

### 5.3 Example layout (multi-sim)

```
/work/pseudo/
  p21860/
    preprocess/ …  simsetup/ …  hpc/ …  analysis/ …  reporter/ …
  p21860_ATP_MG/
    …
  q8iv63/
    …
  analysis/                    # combined overlays + DSSP comparison
  reporter/
    combined_report.html
  run_summary.md
  agent_conversation.log
```

---

## 6. Simulation parameters

### Production length

State duration explicitly in the goal:

```bash
--goal "... run 100 ns MD simulation ..."
```

The setup agent maps this to `nsteps` in `md.mdp`.

### Force field and water model

```bash
python SimAgent.py \
  --goal "Setup MD for kinase.pdb for 20 ns" \
  --working-dir work_ff \
  --subtask preprocess simsetup \
  --force-field amber99sb-ildn \
  --water-model tip3p
```

Defaults: `amber99sb-ildn`, TIP3P, 310 K, 1 bar, 0.15 M NaCl — unless
overridden in the goal or via CLI flags.

Box type, ion strategy, and equilibration details can also be set in natural
language (e.g. *"dodecahedron box, 1.0 nm clearance"*, *"neutralize only, no
added salt"*). See README for a published MLKL validation example.

---

## 7. LLM setup

LLM planning is **enabled by default**. SimAgent’s conda env only includes the
**Python client**. Install the **Ollama server** and pull **`gpt-oss:20b`**
separately — full steps: **[docs/OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md)**.

### Quick local check

```bash
# Terminal A
ollama serve

# Terminal B
ollama pull gpt-oss:20b   # once
curl -s http://127.0.0.1:11434/api/tags
python SimAgent.py \
  --goal "Setup MD for protein.pdb" \
  --working-dir working_dir \
  --llm-base-url http://127.0.0.1:11434 \
  --llm-model gpt-oss:20b
```

### Remote / private endpoint

```bash
--llm-base-url http://your-host:11434 --llm-model gpt-oss:20b
```

### Key-based providers

The CLI has no `--api-key` flag. Use an internal gateway that exposes an
Ollama-compatible API and point `--llm-base-url` at that proxy.

### Without LLM

Use `--no-llm` for deterministic heuristic routing (offline testing or when no
endpoint is available):

```bash
python SimAgent.py --goal "..." --no-llm
```

---

## 8. Resume and retry

When one or more multi-sim jobs fail, retry **only failed simulations** without
redoing successes.

**Requirements:**

- Same `--working-dir` as the original run
- Same `--goal` and PDB list so simulation **labels** match

| Flag | Effect |
|------|--------|
| `--resume` | Skip sims with `success=True`; re-run failures |
| `--retry-labels LABEL …` | Force-retry specific labels even if marked succeeded |

**Example — one simulation failed:**

```bash
python SimAgent.py \
  --goal "... (same goal as original) ..." \
  --working-dir pseudo \
  --subtask preprocess simsetup hpcjob \
  --resume
```

**Example — wrong HPC walltime; force retry:**

```bash
python SimAgent.py \
  --goal "... (same goal) ..." \
  --working-dir pseudo \
  --subtask preprocess simsetup hpcjob \
  --resume \
  --retry-labels p21860_ATP_MG q8nb16_ATP_MG
```

The supervisor reads `supervisor/state.jsonl` and per-sim checkpoints, prints a
retry plan to `agent_conversation.log`, runs only RERUN labels, then proceeds
to combined analysis when all sims complete.

---

## 8.1 Unsupervised classification (multi-simulation)

Use when you have finished trajectories and want a **numeric feature matrix** for
clustering — without manual labels.

**Important:** The framework builds `classification_features.csv` when your
`--goal` requests classification / clustering / a feature matrix, **or** when it
describes family modular comparative descriptors (pocket COM/orientation,
consensus RMSF, χ₁, N↔C DCCM, dihedral PCA entropy, hierarchical heatmap).
Ordinary overlay-only combined analysis does **not** create this file.

**Classic binding + Cartesian FEL example:**

```bash
python SimAgent.py \
  --goal "All trajectories under ./agenticB5R1/<label>/ are complete. Per simulation: ligand pocket distance, protein–ATP contacts, pocket SASA, residence/unbinding, pocket RMSF, ligand RMSF, PCA, FEL, and FEL basin features. Then unsupervised classification across all systems (feature table + z-score CSV). Combined: overlay pocket distance and RMSF." \
  --working-dir ./agenticB5R1 \
  --subtask analysis reporter
```

**Family modular example** (scientific descriptors; LLM selects columns):

```bash
python SimAgent.py \
  --goal "Use KAPCA (p17612) as the reference pocket (15 Å of ATP), map via MSA.
          Extract: ATP–pocket COM mean/std, axis orientation mean/std, consensus
          Cα RMSF mean/std, pocket χ₁, N↔C DCCM, independent dihedral PCA
          landscape entropy. Hierarchical dendrogram with feature heatmap;
          do not fix k." \
  --working-dir ./pseudokin_5x2/run_01 \
  --rep-num 2 \
  --subtask analysis reporter \
  --combined-only
```

**Outputs** (when classification is requested):

| File | Purpose |
|------|---------|
| `{base}/analysis/classification_features.csv` | Raw scalars — one row per system |
| `{base}/analysis/classification_features_zscore.csv` | Robust/IQR or classic z-scores — clustering input |
| `{base}/analysis/classification_feature_selection.json` | LLM-chosen columns + scientific reasoning |
| `{base}/analysis/classification_dendrogram_heatmap.png` | Dendrogram + feature heatmap panel |
| `{base}/analysis/classification_features.json` | Column list and metric groups used |

Use the **z-score** file for clustering. Prefer scientific wording in the goal;
the LLM may keep a paper-like subset or a slightly larger/smaller set with
written rationale. Details: [docs/ANALYSIS_TOOLS.md](docs/ANALYSIS_TOOLS.md).

---

## 9. Reading run outputs

### Terminal summary

Printed at workflow exit:

```
============================================================
WORKFLOW RUN SUMMARY
============================================================
  Mode: multi_simulation
  Working directory: /work/pseudo
  Simulations: 8 total
  Succeeded: 7
  Skipped:   1
  Failed:    0
  ...
============================================================
```

### `run_summary.md`

Best first stop after a run: mode, per-simulation status, job IDs, skip reasons,
and pointers to key artifacts.

### `agent_conversation.log`

Full audit trail. Useful search terms:

| Term | What you find |
|------|----------------|
| `SUPERVISOR ROUTING` | Next agent and reason |
| `master plan` | Multi-sim per-case prompts |
| `LLM INTERACTION` | Prompts and responses |
| `[combined_only]` | Combined-only discovery path |
| `[resume]` | Retry plan |

### HTML reports

- **Per-sim:** `{label}/reporter/report.html`
- **Multi-sim:** `{working-dir}/reporter/combined_report.html`

---

## 10. Troubleshooting

### Holo simulation skipped (AlphaFold source)

Expected when ligands are absent. Use an experimental PDB with co-crystal ligands,
or dock ligands before running. Skip reason is in `run_summary.md`.

### Simulation time ignored

Include explicit `NN ns` in the goal. Verify `nsteps` in `simsetup/md.mdp` after setup.

### Multi-case run did not expand into separate directories

Use explicit case phrasing for apo/holo expansion.

### `--combined-only` starts per-sim analysis instead

Ensure each `{label}/analysis/analysis_summary.jsonl` exists. Use the same
`--working-dir` as the original study. Recent versions persist the
`combined_only` flag through the workflow state.

### Missing DSSP heatmap for one simulation (e.g. VRK3 apo)

That per-sim run may not have executed DSSP. Re-run with `--subtask analysis`
for that label, or use `--combined-only` — combined analysis backfills missing
DSSP from `hpc/mdWrap.xtc` when available.

### `dssp_comparison.png` not found

It is written to **`{working-dir}/analysis/dssp_comparison.png`**, not inside
per-sim folders. Regenerate via combined analysis or `--combined-only`.

### `--resume` re-runs all sims

| Cause | Fix |
|-------|-----|
| Different `--working-dir` | Use the original base directory |
| Missing `supervisor/state.jsonl` | Disk scan uses per-sim state; add `--retry-labels` if needed |
| Goal/PDB list changed labels | Keep goal and PDB list identical |

### Resumed run skips a sim that needs re-run

Add the label to `--retry-labels` with `--resume`.

---

## 11. Best practices

1. **One study, one `--working-dir`** — keeps artifacts and checkpoints together.
2. **Be explicit in the goal** — duration, case split (apo/holo), residue windows, protein names for literature.
3. **Use one campaign `--working-dir`** for any multi-protein or multi-case project; each system lands in `{label}/`.
4. **Name proteins in the goal** — e.g. `p21860: ERBB3` — for literature and report labels.
5. **Stage incrementally** — `--subtask preprocess simsetup` before adding `hpcjob`.
6. **Check artifacts before re-running** — read `run_summary.md` and key files under `analysis/`.
7. **Use `--combined-only`** when per-sim analysis is done and you only need overlays + report.
8. **For family classification, write science not schema** — COM/orientation/RMSF/χ₁/DCCM/entropy
   in plain language; let modular tools + LLM feature selection assemble the matrix.
9. **Use `--rep-num 2` (or more)** when you want replicate-averaged dynamics features.

---

## Further reading

| Document | Contents |
|----------|----------|
| [README.md](README.md) | Overview, quick start, force fields, classification examples |
| [docs/PROJECT.md](docs/PROJECT.md) | Product overview, layout, CLI, run outputs |
| [docs/PIPELINE_WORKFLOW.md](docs/PIPELINE_WORKFLOW.md) | Agent order, directories, flag examples |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | LangGraph pipeline and multi-sim design |
| [docs/ANALYSIS_TOOLS.md](docs/ANALYSIS_TOOLS.md) | Analysis tools, modular dynamics, classification |
| [docs/TOOLS.md](docs/TOOLS.md) | Dependencies and MD mechanisms |
| [docs/POOLS.md](docs/POOLS.md) | Local workers and SLURM HPC pool |
| [docs/OLLAMA_SETUP.md](docs/OLLAMA_SETUP.md) | Ollama server + `gpt-oss:20b` install |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Contributor coding rules |
