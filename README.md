# AgenticAI — LLM-Powered MD Workflow

An LLM-powered, multi-agent system for molecular dynamics (MD) simulation
workflows. It interprets natural-language goals and orchestrates the full
pipeline — preprocessing, setup, HPC submission, analysis, and reporting —
with optional human-in-the-loop checkpoints. When the LLM is unavailable it
falls back to heuristic routing.

## Features

- **Natural-language goals** — describe what you want; the supervisor extracts
  PDB paths, parameters, and which steps to run or skip.
- **Multi-agent pipeline** — preprocess → setup → HPC → analysis → reporter.
- **Multi-simulation mode** — run many PDbs (or apo/holo cases) in parallel,
  then auto-generate cross-simulation comparisons and a combined report.
- **Subtask control** — run only the stages you need (e.g. `analysis reporter`).
- **Resumable** — re-run only failed simulations, or regenerate just the
  combined analysis/report from existing outputs.

## Project structure

```
agentic/
├── supervisor/   # Orchestration, routing, multi-sim master plan
├── planner/      # LLM-guided execution planning
├── preprocess/   # PDB cleaning, water removal, hydrogen addition
├── simsetup/     # Topology + MDP generation
├── hpc/          # Job submission, monitoring, downloads
├── analysis/     # Trajectory analysis (RMSD, RMSF, Rg, DCCM, DSSP, …)
├── reporter/     # HTML reports + literature review
├── programmer/   # Script generation
└── utils/        # Logging, visualization, shared helpers

src/               # Reusable analysis/setup tools (imported by agents)
run_agenticAIWork.py   # Main CLI entry point
docs/              # User guides and workflow documentation
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick start

Run without an LLM (heuristic mode):

```bash
python run_agenticAIWork.py \
  --goal "Run an MD simulation of my_project/protein.pdb in water with 150 mM NaCl" \
  --working-dir my_project \
  --no-human-loop
```

Run with LLM planning (Ollama endpoint):

```bash
python run_agenticAIWork.py \
  --goal "Prepare MD simulation for ATP.pdb with AMBER force field" \
  --working-dir working_dir/ATP \
  --use-llm --llm-base-url http://127.0.0.1:11434 --llm-model gpt-oss:20b \
  --no-human-loop
```

## Command-line options

| Flag | Description |
|------|-------------|
| `--goal TEXT` | **Required.** Natural-language description of the goal. |
| `--working-dir PATH` | Base directory; agents use subdirs (`preprocess/`, `hpc/`, `analysis/`, …). |
| `--subtask AGENT …` | Run only specific stages: `preprocess simsetup hpcjob analysis reporter`. |
| `--simtype {singlesim,multisim}` | Force single- or multi-simulation mode (default: `singlesim`, auto-detected). |
| `--pdb-list PDB …` | Multiple input PDbs (activates multi-sim). |
| `--sim-dirs DIR …` | Existing per-simulation directories for analysis of completed runs. |
| `--max-concurrent N` | Max concurrent simulations in multi-sim mode (default: 4). |
| `--resume` | Re-run only the simulations that previously failed. |
| `--retry-labels LABEL …` | Force-retry specific labels even if recorded as succeeded. |
| `--combined-only` | Discover sims via `{label}/analysis/analysis_summary.jsonl`; run only base-level combined analysis + report (no per-sim re-analysis). |
| `--use-llm` | Enable LLM-powered planning (recommended). |
| `--llm-model TEXT` | LLM model name (default: `gpt-oss:20b`). |
| `--llm-base-url TEXT` | LLM endpoint URL (default: `http://localhost:11434`). |
| `--force-field TEXT` | Override force field (default: `amber99sb-ildn`). |
| `--water-model TEXT` | Override water model (default: `tip3p`). |
| `--no-human-loop` | Disable human checkpoints (autonomous execution). |

## Subtasks

Use `--subtask` to run part of the pipeline. Stages run in order.

```bash
# Preprocess + setup + submit (no analysis)
python run_agenticAIWork.py --goal "…" --working-dir work_dir \
  --subtask preprocess simsetup hpcjob --use-llm --no-human-loop

# Analyse an existing trajectory, then report
python run_agenticAIWork.py \
  --goal "Trajectory in working_dir/hpc/ (md.xtc, md.gro). Compute RMSD, RMSF, COM and DSSP, then write a report." \
  --working-dir working_dir \
  --subtask analysis reporter --use-llm --no-human-loop
```

Analysis reads trajectories from `working_dir/hpc/` and writes results to
`working_dir/analysis/`.

## Multi-simulation mode

Each PDB (or case) gets its own pipeline in a separate directory. After all
simulations finish, a combined analysis produces comparative plots, statistical
tables, and an LLM-generated HTML report.

Multi-sim activates in any of these ways:

| Method | When to use |
|--------|-------------|
| `--simtype multisim` | Explicit selection. |
| `--pdb-list a.pdb b.pdb` | Fresh simulations from PDB files. |
| `--sim-dirs dir1 dir2` | Analyse already-completed simulations. |
| Multiple PDbs in `--goal` | Auto-detected. |

Example — fresh multi-sim from PDB files:

```bash
python run_agenticAIWork.py \
  --goal "Run 100 ns MD at 310 K and analyse RMSD, RMSF, and secondary structure" \
  --pdb-list protein_a.pdb protein_b.pdb protein_c.pdb \
  --working-dir multi_run \
  --use-llm --no-human-loop --max-concurrent 4
```

Example — analyse existing simulations:

```bash
python run_agenticAIWork.py \
  --goal "Simulations for 1A, 2B, 3C are done in their subdirectories. Analyse trajectories and compare RMSD and Rg." \
  --working-dir multi_run \
  --sim-dirs multi_run/1A multi_run/2B multi_run/3C \
  --subtask analysis reporter --use-llm --no-human-loop
```

### Component-case expansion

A single goal can request multiple cases from the same PDB — for example
"two different cases: 1. Protein only, 2. Protein + ATP + MG". The supervisor
expands each PDB into separate simulations with their own directories:

- `p21860` — protein-only case
- `p21860_ATP_MG` — protein + ATP + MG case

For 4 PDbs × 2 cases, 8 simulations are created. Each per-simulation prompt
tells preprocessing/setup which components to keep or remove.

### Resume, retry, and combined-only

When some simulations fail, re-run only those (the same `--working-dir` must be
used so prior state is found):

| Flag | Effect |
|------|--------|
| `--resume` | Re-run simulations recorded as failed; skip the rest. |
| `--retry-labels LABEL …` | Force-retry specific labels regardless of stored status. |
| `--combined-only` | Skip per-sim analysis; rebuild only the combined analysis + report from existing outputs. |

```bash
# Re-run one failed case, then regenerate the combined report
python run_agenticAIWork.py --goal "…same goal as the original run…" \
  --working-dir pseudo --simtype multisim \
  --subtask analysis reporter --use-llm --no-human-loop \
  --resume --retry-labels q8nb16_ATP_MG

# Regenerate only the combined analysis + report (no per-sim re-analysis)
python run_agenticAIWork.py --goal "…same goal as the original run…" \
  --working-dir pseudo --simtype multisim \
  --subtask analysis reporter --combined-only \
  --use-llm --no-human-loop
```

## Directory layout

```
multi_run/
├── protein_a/                              # Per-simulation (individual analysis)
│   ├── analysis/analysis_summary.jsonl     # ← per-sim metrics (read by combined stage)
│   ├── hpc/
│   └── reporter/
├── protein_b/ …
├── analysis/                               # Combined cross-simulation plots
└── reporter/combined_report.html           # Combined HTML report
```

With `--combined-only`, the framework scans each `{label}/analysis/analysis_summary.jsonl` and writes combined outputs only to the base-level `analysis/` and `reporter/` folders — it does not re-run per-simulation analysis.

## HPC with Ollama

On an HPC node with a running Ollama server:

```bash
srun --jobid=YOUR_JOB_ID --pty bash
conda activate ~/conda_envs/ollama_env/
curl -s http://127.0.0.1:11434/api/tags        # verify server + models
export PYTHONDONTWRITEBYTECODE=1                # avoid bytecode cache issues on NFS

python run_agenticAIWork.py \
  --goal "…" \
  --working-dir working_dir \
  --use-llm --llm-base-url http://127.0.0.1:11434 --llm-model gpt-oss:20b \
  --no-human-loop
```

## Documentation

- Architecture: `docs/ARCHITECTURE.md`
- Conventions: `docs/CONVENTIONS.md`
- Project overview: `docs/PROJECT.md`

## License

Choose a license for your project.





##  Example   ##

| Flag | Description |
|------|-------------|
| `--goal TEXT` | **Required.** Natural-language description of the goal. |
| `--working-dir PATH` | Base directory; agents use subdirs (`preprocess/`, `hpc/`, `analysis/`, …). |
| `--subtask AGENT …` | Run only specific stages: `preprocess simsetup hpcjob analysis reporter`. |
| `--simtype {singlesim,multisim}` | Force single- or multi-simulation mode (default: `singlesim`, auto-detected). |
| `--pdb-list PDB …` | Multiple input PDbs (activates multi-sim). |
| `--sim-dirs DIR …` | Existing per-simulation directories for analysis of completed runs. |
| `--max-concurrent N` | Max concurrent simulations in multi-sim mode (default: 4). |
| `--resume` | Re-run only the simulations that previously failed. |
| `--retry-labels LABEL …` | Force-retry specific labels even if recorded as succeeded. |
| `--combined-only` | Discover sims via `{label}/analysis/analysis_summary.jsonl`; run only base-level combined analysis + report (no per-sim re-analysis). |
| `--use-llm` | Enable LLM-powered planning (recommended). |
| `--llm-model TEXT` | LLM model name (default: `gpt-oss:20b`). |
| `--llm-base-url TEXT` | LLM endpoint URL (default: `http://localhost:11434`). |
| `--force-field TEXT` | Override force field (default: `amber99sb-ildn`). |
| `--water-model TEXT` | Override water model (default: `tip3p`). |
| `--no-human-loop` | Disable human checkpoints (autonomous execution). |



```bash
python run_agenticAIWork.py \
  --goal "I want to study the effect of ATP binding in protein dynamics of these four PDBs p21860.pdb, q8iv63.pdb, q8nb16.pdb, q8wz42.pdb which are available in /pseudo/ directory. Each pdb file has protein + ATP + MG. Please preprocess and setup MD Simulation for 100 ns of all Pdbs with two different cases: 1. Protein only, 2. Protein + ATP + MG therefore total 8 simulations. Once the simulation setups are done please submit the job in HPC. The simulated protein are human pseudokinases and the name of pseudokinase in the uniprotid are p21860: ERBB3, q8iv63: VRK3, q8nb16: MLKL, q8wz42: TITIN. For each system compute: (1) backbone RMSD over time to assess structural stability, (2) per-residue RMSF to identify flexible and rigid regions, Also the RMSF bar plot near active sites (resid 150 to 200) (3) radius of gyration to monitor compactness, (4) center-of-mass distance between the bound ATP ligand and the catalytic pocket (pocket defined as all protein atoms within 5 Å of ATP at frame 0) to track binding-site stability, (5) Dynamic Cross-Correlation Matrix (DCCM) of Cα fluctuations to reveal correlated and anti-correlated residue motions and allosteric communication networks, DCCM diffs in holo and apo form of protein and (6) secondary structure (DSSP) time evolution of whole protein and active sites (resid 150 to 200) which quantify αC-helix and activation-loop structural dynamics. After per-simulation analysis, generate comparative overlay plots and statistical tables across all pseudokinases. For the reporter agent, retrieve relevant literature for each pseudokinase with its given name focusing on activation-loop conformations, allosteric regulation, and dynamics from MD simulations or experimental. Correlate findings results from simulation with literature in the final report." \
  --working-dir pseudo \
  --subtask analysis reporter \
  --simtype multisim \
  --use-llm --no-human-loop \
  --combined-only




python run_agenticAIWork.py \
  --goal "I want to study the dynamics of the N-terminal segment of chain B in the two PDBs, dclk3_psma3_in.pdb and dclk3_psma3_less_out.pdb, which are available in the /dclk_PSMA/ directory. Please preprocess and set up 100 ns MD simulations for both PDBs, for a total of 2 simulations, and submit the jobs on the HPC after setup. The main focus is chain B residues 1 to 34 and how this segment interacts with nearby residues in chain A. For each simulation, compute backbone RMSD over time for the whole complex and for chain B residues 1 to 34. Compute per residue RMSF for chain B residues 1 to 34. At frame 0, identify all chain A residues within 10 Å of chain B residues 1 to 34, then compute RMSF for only those chain A residues throughout the trajectory. Also track the center of mass distance and minimum heavy atom distance between chain B residues 1 to 34 and those nearby chain A residues over time to determine whether the N terminal segment remains associated with chain A or moves away. Finally, generate comparative plots and statistical tables for dclk3_psma3_in.pdb versus dclk3_psma3_less_out.pdb, focusing on RMSD, RMSF, contact stability, and distance changes. In the final report, summarize which structure shows greater movement of chain B residues 1 to 34, whether this segment remains close to chain A, and whether nearby chain A residues become more or less flexible during the simulations." \
  --working-dir dclk_PSMA \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim \
  --use-llm --no-human-loop





  ```