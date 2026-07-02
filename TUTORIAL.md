# AgenticAI Tutorial — End-to-End Usage Guide

This guide walks you from installation through common workflows: single and
multi-simulation studies, analysis-only reruns, combined reporting, and
troubleshooting. For a short overview, see [README.md](README.md).

---

## Table of contents

1. [How a run works](#1-how-a-run-works)
2. [Prerequisites](#2-prerequisites)
3. [Core CLI flags](#3-core-cli-flags)
4. [Workflow recipes](#4-workflow-recipes) (including [HPC pool](#48-full-multi-sim-pipeline-with-hpc-pool))
5. [Artifacts — what gets produced](#5-artifacts--what-gets-produced)
6. [Simulation parameters](#6-simulation-parameters)
7. [LLM setup](#7-llm-setup)
8. [Resume and retry](#8-resume-and-retry)
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
| **Analysis** | Analysis | RMSD, RMSF, Rg, DCCM, DSSP, overlays |
| **Report** | Reporter | HTML report + literature |

Use `--subtask` to run only the stages you need (e.g. `analysis reporter` on
finished trajectories). In **multi-simulation** mode (`--simtype multisim`),
the supervisor loops over each simulation directory, then runs **combined
analysis** and a **combined HTML report** at the base `--working-dir`.

When the full pipeline runs in multi-sim mode (preprocess through reporter),
the **cross-sim HPC pool** uses three explicit stages:

1. **Prep all** — preprocess + simsetup for every PDB (sequential).
2. **HPC pool** — submit and monitor up to `--allowed-hpc-jobs` SLURM jobs in parallel.
3. **Post-HPC all** — per-sim analysis + reporter, then combined outputs at `{base}/`.

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
python run_agenticAIWork.py --goal "..." [options]
```

| Flag | Description |
|------|-------------|
| `--goal` | Natural-language task (**required**) |
| `--working-dir` | Base directory for all outputs |
| `--subtask` | Agents to run: `preprocess simsetup hpcjob analysis reporter` |
| `--simtype` | `singlesim` (default) or `multisim` |
| `--pdb-list` | Explicit PDB list for multi-sim |
| `--sim-dirs` | Existing per-sim directories (analysis-only multi-sim) |
| `--no-llm` | Disable LLM planning (deterministic fallback) |
| `--llm-model` | Model name (default `gpt-oss:20b`) |
| `--llm-base-url` | Endpoint URL (default `http://localhost:11434`) |
| `--HITL` | `error` or `all` — enable human-in-the-loop (default: off) |
| `--force-field` | Override force field (default `amber99sb-ildn`) |
| `--water-model` | Override water model (default `tip3p`) |
| `--allowed-hpc-jobs` | Max concurrent SLURM jobs in cross-sim HPC pool (default `5`) |
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
python run_agenticAIWork.py \
  --goal "Preprocess and setup MD for my_protein.pdb for 50 ns, then submit to HPC" \
  --working-dir /work/s1 \
  --subtask preprocess simsetup hpcjob \
  --simtype singlesim
```

### 4.2 UniProt accession (no local PDB)

The framework can download from AlphaFold (default) or RCSB and extract a domain
via UniProt:

```bash
python run_agenticAIWork.py \
  --goal "Study ATP binding dynamics of UniProt P21860 (ERBB3).
          Download the AlphaFold PDB, extract the kinase domain,
          and run 1 ns MD for two cases: 1. Protein only, 2. Protein + ATP + MG.
          Submit both jobs to HPC." \
  --working-dir /work/erbb3 \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim
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
python run_agenticAIWork.py \
  --goal "Run 100 ns MD for each pseudokinase and submit to HPC.
          Names: p21860=ERBB3, q8iv63=VRK3, q8nb16=MLKL, q8wz42=TITIN." \
  --pdb-list p21860.pdb q8iv63.pdb q8nb16.pdb q8wz42.pdb \
  --working-dir /work/pseudo \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim
```

### 4.4 Component-case expansion (apo vs holo from same PDB)

Use explicit phrasing — *"two different cases"*, *"1. Protein only"*,
*"2. Protein + ATP + MG"*:

```bash
python run_agenticAIWork.py \
  --goal "Study ATP binding for p21860.pdb, q8iv63.pdb, q8nb16.pdb.
          For each PDB run two cases: 1. Protein only, 2. Protein + ATP + MG.
          Total 6 simulations. Preprocess, setup, and submit to HPC." \
  --working-dir /work/pseudo \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim
```

Expected layout: `p21860/`, `p21860_ATP_MG/`, `q8iv63/`, `q8iv63_ATP_MG/`, …

### 4.5 Per-simulation analysis + report (trajectories already finished)

**Single simulation:**

```bash
python run_agenticAIWork.py \
  --goal "Simulation is complete in /work/s1/hpc. Compute RMSD, RMSF, Rg,
          DCCM, DSSP, and generate the report." \
  --working-dir /work/s1 \
  --subtask analysis reporter
```

**Multi-simulation** (full per-sim loop, then combined report):

```bash
python run_agenticAIWork.py \
  --goal "Analyse all completed pseudokinase simulations. Compute RMSD, RMSF, Rg,
          DCCM apo vs holo difference, RMSF for activation loop residues 150-200,
          ATP pocket COM distance, and DSSP for the activation loop.
          Generate combined comparison report with literature." \
  --working-dir /work/pseudo \
  --subtask analysis reporter \
  --simtype multisim
```

**Analysis from existing directories** (`--sim-dirs`):

```bash
python run_agenticAIWork.py \
  --goal "Compare structural dynamics across completed simulations." \
  --sim-dirs /work/pseudo/p21860 /work/pseudo/p21860_ATP_MG \
  --working-dir /work/pseudo \
  --subtask analysis reporter \
  --simtype multisim
```

### 4.6 Combined analysis + report only (`--combined-only`)

When **every simulation already has** `analysis/analysis_summary.jsonl`, skip
the per-sim loop and jump straight to cross-simulation overlays and the HTML report:

```bash
python run_agenticAIWork.py \
  --goal "Generate combined comparison plots and multi-simulation report
          for completed pseudokinase runs (ERBB3, VRK3, MLKL, TITIN)." \
  --working-dir /work/pseudo \
  --subtask analysis reporter \
  --simtype multisim \
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

1. **Prep (sequential)** — each sim runs preprocess and simsetup one at a time.
2. **HPC pool (parallel)** — up to `--allowed-hpc-jobs` SLURM jobs run at once.
3. **Poll** — the workflow sleeps and re-checks SLURM every `--hpc-check-interval`.
4. **Post-HPC (sequential)** — per-sim analysis and reporter, then combined analysis + report.

```bash
python run_agenticAIWork.py \
  --goal "Run 1 ns MD for p23458 (JAK1), p29597 (TYK2), q7rtn6 (STRAA).
          Compare RMSF and ligand pocket distance across simulations.
          DCCM for JAK1 and TYK2 only." \
  --working-dir ./my_study \
  --simtype multisim \
  --allowed-hpc-jobs 4 \
  --hpc-check-interval 3m
```

If the process is interrupted during HPC, restart with the same `--working-dir`
and `--resume`. Pool state in `supervisor/state.jsonl` restores job IDs and prep
status. See [docs/HPC_POOL.md](docs/HPC_POOL.md).

Use `--HITL error` to pause on SLURM submit failures or terminal job states;
use `--HITL all` to review after every stage.

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
| `analysis/` | **Combined** overlay plots, DCCM panels, DSSP comparison |
| `reporter/combined_report.html` | Multi-simulation HTML report (multi-sim only) |
| `planner/master_plan.md` | Cross-simulation plan and per-case prompts |

### 5.2 Per-simulation directory (`{working-dir}/{label}/`)

Each simulation (e.g. `p21860/`, `p21860_ATP_MG/`) is isolated:

```
{label}/
  preprocess/     # cleaned PDB, protonated structures, component splits
  simsetup/       # topol.top, *.gro, *.mdp
  hpc/            # SLURM script, *.xtc, *.edr, job logs
  analysis/       # per-sim plots, *.dat, analysis_summary.jsonl
  reporter/       # per-sim report.html
  planner/        # execution_plan.md
  supervisor/     # per-sim state checkpoint
  agent_conversation.log
```

**Key analysis artifacts** (under `{label}/analysis/`):

- `analysis_summary.jsonl` — structured record of every analysis step (required for `--combined-only`)
- `rmsd.png`, `rmsf.png`, `rg.png`, `dccm_heatmap.png`
- `dssp_raw_data.dat`, `dssp_heatmap.png` (when DSSP was run)

**Key combined artifacts** (under `{working-dir}/analysis/`):

- `rmsd_overlay.png`, `rmsf_apo_holo_*.png`, `dccm_apo_holo_*_panels.png`
- `dssp_comparison.png` — helix/sheet/coil bar chart across all sims
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
python run_agenticAIWork.py \
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

LLM planning is **enabled by default**. Point `--llm-base-url` and `--llm-model`
at your Ollama-compatible endpoint.

### Local Ollama

```bash
python run_agenticAIWork.py \
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
python run_agenticAIWork.py --goal "..." --no-llm
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
python run_agenticAIWork.py \
  --goal "... (same goal as original) ..." \
  --working-dir pseudo \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim \
  --resume
```

**Example — wrong HPC walltime; force retry:**

```bash
python run_agenticAIWork.py \
  --goal "... (same goal) ..." \
  --working-dir pseudo \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim \
  --resume \
  --retry-labels p21860_ATP_MG q8nb16_ATP_MG
```

The supervisor reads `supervisor/state.jsonl` and per-sim checkpoints, prints a
retry plan to `agent_conversation.log`, runs only RERUN labels, then proceeds
to combined analysis when all sims complete.

---

## 8.1 Unsupervised classification (multi-simulation)

Use when you have many finished trajectories (e.g. 35 protein–ATP systems at ~200 ns)
and want a **numeric feature matrix** for clustering — without manual labels.

**Important:** The framework builds `classification_features.csv` **only** when your
`--goal` explicitly requests classification, clustering, unsupervised grouping, or a
feature matrix. Ordinary combined analysis (overlays, comparison tables) does **not**
create this file.

**Full feature set example:**

```bash
python run_agenticAIWork.py \
  --goal "All trajectories under ./agenticB5R1/<label>/ are complete (~200 ns). Per simulation: ligand pocket distance, protein–ATP contacts, pocket SASA, residence/unbinding, pocket RMSF, ligand RMSF, PCA, FEL, and FEL basin features. Then unsupervised classification across all systems (feature table + z-score CSV). Combined: overlay pocket distance and RMSF." \
  --working-dir ./agenticB5R1 \
  --subtask analysis reporter \
  --simtype multisim
```

**Subset example** (only RMSF + pocket distance are analyzed and featurized):

```bash
python run_agenticAIWork.py \
  --goal "Per simulation compute RMSF and ligand pocket distance only. Unsupervised classification using those features across all systems." \
  --working-dir ./agenticB5R1 \
  --subtask analysis reporter \
  --simtype multisim
```

**Outputs** (when classification is requested):

| File | Purpose |
|------|---------|
| `{base}/analysis/classification_features.csv` | Raw scalars — one row per protein |
| `{base}/analysis/classification_features_zscore.csv` | Z-scores for k-means / hierarchical clustering |
| `{base}/analysis/classification_features.json` | Column list and metric groups used |

Use the **z-score** file for clustering (scales differ between contacts, entropy, etc.).
Details: [docs/ANALYSIS_TOOLS.md](docs/ANALYSIS_TOOLS.md).

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

Use explicit case phrasing and `--simtype multisim`.

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
3. **Use `--simtype multisim`** for any multi-protein or multi-case project.
4. **Name proteins in the goal** — e.g. `p21860: ERBB3` — for literature and report labels.
5. **Stage incrementally** — `--subtask preprocess simsetup` before adding `hpcjob`.
6. **Check artifacts before re-running** — read `run_summary.md` and key files under `analysis/`.
7. **Use `--combined-only`** when per-sim analysis is done and you only need overlays + report.

---

## Further reading

| Document | Contents |
|----------|----------|
| [README.md](README.md) | Overview, quick start, force fields |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | LangGraph pipeline and multi-sim design |
| [docs/TOOLS.md](docs/TOOLS.md) | Agent tool catalogue |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Naming and development conventions |
| [docs/PROJECT.md](docs/PROJECT.md) | Extended project overview |
