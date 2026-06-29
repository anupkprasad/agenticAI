# AgenticAI — LLM-Powered Molecular Dynamics Workflow

AgenticAI automates GROMACS molecular dynamics (MD) workflows using LLM-powered
planning, multi-agent orchestration, and optional human-in-the-loop checkpoints.

Given a natural-language goal and either a PDB file or a UniProt accession, the
system can:

1. Resolve protein structures (AlphaFold, RCSB) and extract domains via UniProt
2. Preprocess structures (component separation, protonation, phosphorylation mapping)
3. Build simulation systems (topology, solvation, ions, MDP files)
4. Submit and monitor HPC jobs (SLURM)
5. Analyse trajectories (RMSD, RMSF, Rg, DCCM, DSSP, COM distances)
6. Produce HTML reports with literature references and interactive 3D views

**Full usage guide:** [TUTORIAL.md](TUTORIAL.md)

---

## Key Features

- **Natural-language goals** — describe what you want; agents build a concrete plan
- **UniProt / AlphaFold integration** — start from an accession without a local PDB
- **Multi-simulation mode** — run several proteins or component cases in one study
- **Holo feasibility guard** — skips holo cases when ligands are missing (e.g. AlphaFold)
- **Phosphorylated proteins** — SEP/TPO/PTR stay in the protein chain; mapped for
  CHARMM36 (SP2/THP/TP2), not parameterized as separate ligands
- **Supervisor → Planner → Agents** — validated routing, planner-owned master plans, and tool-based execution
- **Resume / retry** — re-run failed multi-sim jobs without redoing successes
- **Cross-sim HPC pool** — prep sequentially, submit up to N SLURM jobs in parallel, then post-HPC analysis ([docs/HPC_POOL.md](docs/HPC_POOL.md))

---

## Prerequisites

```bash
conda env create -f environment.yml
conda activate ollama_env
```

Optional: confirm your LLM endpoint is reachable (LLM planning is **on by default**):

```bash
curl -s http://127.0.0.1:11434/api/tags
```

Use `--no-llm` only for offline or deterministic fallback runs.

**GROMACS** is included in the conda environment. For phosphorylated proteins with
CHARMM36, install `charmm36-jul2022.ff` (see [Force fields](#force-fields)).

---

## Quick Start

### Single simulation from a local PDB

```bash
python run_agenticAIWork.py \
  --goal "Preprocess and setup MD for my_protein.pdb for 50 ns, then submit to HPC" \
  --working-dir /work/run1 \
  --subtask preprocess simsetup hpcjob
```

### UniProt accession (download + domain extraction)

```bash
python run_agenticAIWork.py \
  --goal "Study ATP binding of UniProt P21860 (ERBB3). Download AlphaFold PDB,
          extract kinase domain, run 1 ns MD for protein-only and protein+ATP+MG.
          Submit to HPC." \
  --working-dir /work/erbb3 \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim
```

### Multi-protein comparative study

```bash
python run_agenticAIWork.py \
  --goal "Run 100 ns MD for each pseudokinase and submit to HPC.
          Names: p21860=ERBB3, q8iv63=VRK3, q8nb16=MLKL, q8wz42=TITIN." \
  --pdb-list p21860.pdb q8iv63.pdb q8nb16.pdb q8wz42.pdb \
  --working-dir /work/pseudo \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim
```

### Analysis-only on completed trajectories

```bash
python run_agenticAIWork.py \
  --goal "Compute RMSD, RMSF, Rg, DCCM, DSSP and generate the report." \
  --working-dir /work/run1 \
  --subtask analysis reporter
```

More examples (resume, component cases, parameter overrides): [TUTORIAL.md](TUTORIAL.md)

---

## Prompt Engineering Guide

AgenticAI works best when `--goal` describes the scientific intent, the available inputs, the requested workflow stages, and the exact analyses you want. Write the goal as a short paragraph or a few sentences, not as comma-separated metadata. Natural language gives the planner enough context to create per-simulation prompts that downstream agents can follow.

Include these details when they apply:

- **Inputs and labels:** list PDB files, UniProt IDs, simulation directories, and protein names such as `p21860: ERBB3`.
- **Workflow stage:** say whether to preprocess, set up simulation, submit to HPC, analyze completed trajectories, report results, or only run a subset via `--subtask`.
- **Simulation intent:** specify component cases such as protein-only, protein+ATP+MG, mutant vs wild type, phosphorylated vs dephosphorylated, or chain/residue windows.
- **Analysis scope:** name the exact analyses you want. For example, “RMSF only for all simulations” will keep the analysis focused on RMSF. If you ask broadly for “protein dynamics” without naming metrics, the planner may choose appropriate dynamics analyses such as RMSD, RMSF, Rg, DCCM, or interaction distances based on available tools and biological context.
- **Per-metric simulation subsets (multi-sim):** each combined metric can target a different set of simulations. You do not need every metric on every protein. Examples:
  - “RMSF for all four simulations” → combined RMSF overlay uses all sims.
  - “DCCM for JAK1 and TYK2 only” → per-sim DCCM on those two; combined DCCM compares only them.
  - “Radius of gyration for JAK1, TYK2, and ULK4” → Rg per-sim on those three; combined Rg overlay on those three only (STRAA excluded).
- **Combined analysis intent:** ask explicitly for comparison, cross-simulation trends, aggregate plots, or a combined report only when you want base-level combined analysis. Otherwise multi-sim runs focus on the individual simulation plans.
- **COM distance wording (important):** two tools exist — choose the phrasing that matches your intent:
  - **Ligand pocket distance** (recommended for holo kinases): say “ligand pocket distance”, “ATP distance to the catalytic pocket”, or “protein atoms within 5 Å of ATP at frame 0”. Output: `ligand_pocket_distance.csv`.
  - **Whole-protein COM distance:** say “COM distance between the **whole protein** and ATP” or “protein COM to ligand COM”. Output: `com_distance.csv`.
  - Do not mix both unless you explicitly want pocket tracking **and** whole-protein COM.
- **Outputs:** mention required plots, CSV summaries, residue ranges, ligand-pocket definitions, literature context, and report format.

Example multi-metric subset prompt:

```bash
--goal "Trajectories are complete for p23458:JAK1, p29597:TYK2, q7rtn6:STRAA, q96c45:ULK4. Analysis only. For all simulations: RMSF and ligand pocket distance (ATP, 5 Å pocket at frame 0). Combined: overlay RMSF and pocket distance across all four. DCCM for JAK1 and TYK2 only. Radius of gyration for JAK1, TYK2, and ULK4 with a combined Rg plot. Do not run preprocessing or HPC."
```

Example focused analysis prompt:

```bash
--goal "Simulations are already complete for p23458.pdb, p29597.pdb, and p52333.pdb under /scratch/project. Run analysis and reporting only. I want RMSF only for each simulation, with per-residue RMSF plots and a CSV summary for each protein. Do not run preprocessing, setup, HPC, or additional analyses."
```

Example comparative prompt:

```bash
--goal "Analyze completed trajectories for ERBB3, VRK3, MLKL, and TITIN. Compute backbone RMSD, per-residue RMSF, and radius of gyration for each simulation, then create a combined comparison report showing cross-protein trends and shared flexible regions. Include protein names in the report and cite relevant literature."
```

---

## Human-in-the-Loop (HITL)

By default the workflow runs **fully automatically** — no pauses between stages.

Use **`--HITL`** when you want interactive review:

| Mode | Flag | Behavior |
|------|------|----------|
| Off (default) | *(omit flag)* | End-to-end execution with no checkpoints |
| Errors only | `--HITL error` | Pause when a stage fails, on HPC pool submit/SLURM failures, or after max retries |
| All checkpoints | `--HITL all` | Pause after preprocess, setup, HPC, analysis, reporter (and HPC pool when applicable) |

### What you can do at a checkpoint

The terminal opens a **bidirectional chat** with the active field agent:

- **Ask questions** — e.g. “What RMSF files were generated?”, “Show the execution plan”
- **Inspect files** — `show rmsf.dat`, `files`, `list analysis/`, `tools`, `agents`
- **Switch field agent** — `switch analysis`, `switch reporter`, `switch setup`, …  
  Reloads that agent’s domain tools and artifact paths (trajectories, per-sim `state.jsonl`, output dirs).
- **Bind a simulation (multi-sim)** — `switch p23458 analysis` or `switch analysis p23458`  
  Chat and tools use that sim’s directories; session is saved in `state.jsonl` (`hitl_active_agent`, `hitl_target_sim_label`).
- **Delegate tasks** — the agent **runs** your request and returns to the same checkpoint:
  - `run analysis: calculate Rg for JAK1`
  - `run reporter: add a DCCM section to the report`
  - `run: <task>` — uses the currently active agent
  - Multi-sim: `run p23458 analysis: calculate RMSF`
- **Execute in chat** — after `switch p29597 analysis`, describe the task in natural language
  (e.g. `calculate DSSP and plot heatmap for residues 100–120`). The **Analysis agent** builds a
  JSON execution plan (like the normal workflow), runs **all steps**, and writes:
  - `{sim}/analysis/hitl_execution_plan.json` — structured plan
  - `{sim}/analysis/execution_log.txt` — step-by-step log
  - `{sim}/agent_conversation.log` — concise summary (no full JSON dumps)
- **Get clarifications from the agent** — the LLM may ask follow-up questions when your request is ambiguous
- **Recover from errors** — after max retries, use:
  - `recommend: <advice>` — agent retries with your guidance
  - `modify: <changes>` — same, with explicit change instructions
  - `retry` — rerun the stage from scratch
- **Proceed** — `approved` / `continue`
- **Stop** — `exit` / `quit`

At the **reporter** checkpoint you can also say `analysis: …` or `reporter: …` to
re-run those stages with new instructions (full pipeline rerun, not just a single delegated task).

### Multi-sim + HITL tips

| Situation | Recommended command |
|-----------|---------------------|
| First run, pause after each sim’s analysis | `--simtype multisim --HITL all` |
| Automatic run; pause only if something fails | `--HITL error` |
| Per-sim work already done; review combined report interactively | Re-run with `--HITL all` — framework auto-detects existing `analysis/` folders and enters combined-only review |
| Retry only failed sims | Add `--resume` (optionally `--retry-labels p23458`) |
| Re-run combined overlay + report only | `--combined-only` |
| Full multi-sim pipeline with parallel HPC | `--simtype multisim --allowed-hpc-jobs 4 --hpc-check-interval 3m` (see [HPC pool](docs/HPC_POOL.md)) |

State is saved to `{working_dir}/supervisor/state.jsonl` (and per-sim copies under
`{label}/supervisor/`). See [docs/CONVENTIONS.md](docs/CONVENTIONS.md) for resume semantics.

Example (interactive analysis + report on completed trajectories):

```bash
python run_agenticAIWork.py \
  --goal "Analysis only for p23458, p29597, q7rtn6, q96c45 …" \
  --working-dir ./agenticB5R1 \
  --subtask analysis reporter \
  --simtype multisim \
  --HITL all
```

---

## CLI Reference

```bash
python run_agenticAIWork.py --goal "..." [options]
```

| Flag | Default | Description |
|------|---------|-------------|
| `--goal` | *(required)* | Natural-language simulation goal |
| `--working-dir` | `.` | Base output directory |
| `--simtype` | `singlesim` | `singlesim` or `multisim` |
| `--pdb-list` | — | Explicit PDB list for multi-sim |
| `--sim-dirs` | — | Existing sim directories for analysis-only multi-sim |
| `--subtask` | all agents | `preprocess simsetup hpcjob analysis reporter` |
| `--no-llm` | off | Disable LLM planning (deterministic fallback) |
| `--llm-model` | `gpt-oss:20b` | Model name |
| `--llm-base-url` | `http://localhost:11434` | LLM API base URL |
| `--HITL` | off | `error` or `all` — enable human-in-the-loop (default: off) |
| `--force-field` | `amber99sb-ildn` | GROMACS force field (e.g. `charmm36-jul2022`) |
| `--water-model` | `tip3p` | Water model |
| `--max-concurrent` | `4` | Max concurrent sims in multi-sim mode (legacy) |
| `--allowed-hpc-jobs` | `5` | Max concurrent SLURM jobs in cross-sim HPC pool |
| `--hpc-check-interval` | `2h` | SLURM poll interval during HPC pool wait (`2h`, `120m`, `7200`) |
| `--resume` | off | Re-run only failed/incomplete multi-sim jobs |
| `--retry-labels` | — | Force-retry specific simulation labels |
| `--combined-only` | off | Multi-sim: only combined analysis + report |

---

## Force Fields

| Force field | Use case | Notes |
|-------------|----------|-------|
| `amber99sb-ildn` | Default protein MD | TIP3P water; GAFF/ACPYPE for small-molecule ligands |
| `charmm36-jul2022` | CHARMM36 proteins | Recommended for phosphorylated proteins (SP2, THP1, TP2) |

Phosphorylated residues (SEP, TPO, PTR) are kept in `protein.pdb` during
preprocessing. For CHARMM36, names are mapped automatically (SEP→SP2, TPO→THP,
PTR→TP2). Do not use `generate_ligand_parameters` for phospho amino acids.

Install CHARMM36 for GROMACS from the [MacKerell lab](https://mackerell.umaryland.edu/charmm_ff.shtml#gromacs)
into your GROMACS `share/gromacs/top/` directory, then:

```bash
python run_agenticAIWork.py ... --force-field charmm36-jul2022
```

---

## Output Layout

Multi-sim run under `--working-dir /work/pseudo`:

```
/pseudo/
  p21860/
    preprocess/       # protein.pdb, protein_h.pdb, ...
    simsetup/         # topol.top, *.gro, *.mdp
    hpc/              # SLURM script, trajectories
    analysis/         # RMSD, RMSF, DCCM plots
    reporter/         # report.html
    agent_conversation.log
  p21860_ATP_MG/      # or skipped with reason in run_summary
  analysis/           # combined plots when requested by user intent or --combined-only
  reporter/
    combined_report.html
  run_summary.md      # human-readable outcome
  run_summary.json    # structured outcome
  agent_conversation.log
```

---

## Repository Layout

```
run_agenticAIWork.py       # CLI entry point
environment.yml            # Conda environment (ollama_env)
agentic/
  workflow.py              # LangGraph StateGraph orchestration
  supervisor/              # Routing, enrichment, multi-sim loop
  planner/                 # Execution plans + knowledge base
  preprocess/              # Structure download, clean, separate
  simsetup/                # Topology, solvation, MDP generation
  hpc/                     # SLURM submission and monitoring
  analysis/                # Trajectory analysis tools
  reporter/                # HTML reports and literature
src/
  preprocess/              # PDB tools, phospho mapping, remodel
  simsetup/                # GROMACS system builder
  analysis/                # Combined cross-sim analysis
  reporter/                # Report generation
TUTORIAL.md                # End-to-end usage guide
docs/
  ARCHITECTURE.md          # System design
  PROJECT.md               # Extended project overview
  HPC_POOL.md               # Cross-sim HPC pool
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [TUTORIAL.md](TUTORIAL.md) | Step-by-step workflows and troubleshooting |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | LangGraph pipeline and multi-sim design |
| [docs/PROJECT.md](docs/PROJECT.md) | Extended overview and conventions |
| [docs/TOOLS.md](docs/TOOLS.md) | Available agent tools |
| [docs/HPC_POOL.md](docs/HPC_POOL.md) | Cross-sim HPC pool, polling, resume |

---

## Development

```bash
# Deterministic routing (no LLM)
python run_agenticAIWork.py --goal "..." --no-llm

# Custom Ollama endpoint (LLM is on by default)
python run_agenticAIWork.py --goal "..." --llm-base-url http://127.0.0.1:11434

# Interactive checkpoints
python run_agenticAIWork.py --goal "..." --HITL all
```

Tests: `pytest` (see `environment.yml` for dependencies).

---

## License

See repository license file if present. CHARMM36 force field parameters are
distributed separately by the MacKerell lab and are not part of this repository.

---

## Use Case: Published horse MLKL validation (CHARMM36 / TIP3P)

Replicate a typical published MLKL MD protocol:

- CHARMM36 force field, TIP3P water
- Dodecahedral box, ≥ 1.0 nm clearance on all sides, PBC
- PME electrostatics, Verlet cutoff scheme
- Steepest-descent minimization until Fmax &lt; 100 kJ/mol nm⁻¹
- NVT heat to 310 K for 100 ps with position restraints
- NPT at 310 K, 1 bar for 100 ps with position restraints
- Production MD at 2 fs; dephosphorylated ~1739 ns, phosphorylated ~2882 ns

### How this maps to AgenticAI

| Published setting | Pipeline default | What to put in `--goal` |
|-------------------|----------------|-------------------------|
| CHARMM36 | `amber99sb-ildn` | Use `--force-field charmm36-jul2022` |
| TIP3P | `tip3p` | Default (or say “TIP3P water”) |
| Dodecahedron, 1 nm clearance | `cubic`, 1.2 nm | **“dodecahedron box, 1.0 nm distance”** |
| Neutralize with Na⁺/Cl⁻ | Neutralize + 0.15 M NaCl | **“neutralize only, no added salt”** (`ion_concentration=0`) |
| Minim Fmax &lt; 100 | `emtol=100`, steep | Default `minim.mdp` |
| NVT 100 ps, posres, 310 K | 50 000 steps × 2 fs | Default `nvt.mdp` |
| NPT 100 ps, posres, 1 bar | 50 000 steps × 2 fs | Default `npt.mdp` |
| Production 2 fs | `dt=0.002` | Default `md.mdp` |
| Remodelled / strained input | — | **“extended minimization”** (adds `minim2.mdp`; optional, not in every paper) |

**Dodecahedron box:** implemented in `src/simsetup/box_builder.py` via `gmx editconf -bt dodecahedron -d <distance>`. The setup agent passes `box_type` and `box_distance` into `build_simulation_system` → `build_simulation_box`. Supported values: `cubic`, `dodecahedron`, `octahedron` (see `agentic/simsetup/config.yaml`).

**Phosphorylation:** SEP/TPO/PTR stay on the protein chain; CHARMM36 dianionic mapping (SP2/THP2/TP2) runs in preprocess. Do not use ligand parameterization for phospho residues.

**Production length:** `--goal` can set one duration (e.g. `2882 ns`); multisim applies the same `production_ns` to every PDB in one run. For exact 1739 ns vs 2882 ns, either run two separate jobs or edit `md.mdp` / `md.tpr` in one sim’s `simsetup/` after setup.

### Example: horse MLKL dephospho + phospho (multisim)

Place `chain_a_modelled.pdb` and `chain_a_modelled_phos.pdb` under `horse_MLKL/`, then:

```bash
python run_agenticAIWork.py \
  --goal "Replicate published MLKL validation MD: CHARMM36-jul2022 and TIP3P water.
Use a dodecahedron simulation box with 1.0 nm clearance from the protein on all sides.
Neutralize the system with sodium and chloride only (no additional salt concentration).
Temperature 310 K, pressure 1 bar. Steepest descent minimization until Fmax below 100.
NVT equilibration 100 ps and NPT equilibration 100 ps with position restraints on the protein.
Production MD with 2 fs timestep. The structures are remodelled — use extended minimization.
Preprocess and set up simulations for chain_a_modelled.pdb (dephosphorylated) and
chain_a_modelled_phos.pdb (phosphorylated) in horse_MLKL/, then submit HPC jobs.
Production: 1739 ns for dephosphorylated MLKL and 2882 ns for phosphorylated MLKL. Use 7 days waltime of HPC resources" \
  --working-dir horse_MLKL \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim \
  --force-field charmm36-jul2022

```

After simsetup, confirm in each `simsetup/` directory:

- `minim.mdp` / optional `minim2.mdp` (if extended minim triggered)
- `nvt.mdp`, `npt.mdp`, `md.mdp`
- `topol.top`, `system.gro`
- Box geometry in `boxed.gro` header (dodecahedron from `editconf`)

If production lengths must differ, set `nsteps` in `md.mdp` before HPC copy:

- 1739 ns → `nsteps = 869500000` (1739 × 10⁶ / 0.002)
- 2882 ns → `nsteps = 1441000000`

Or re-run simsetup with a single PDB and the matching ns in `--goal` per structure.

### Strict single-stage minimization (paper-style only)

If you do **not** want the extra `minim2` stage, omit “extended minimization” / “remodelled” from the goal and ensure `merged_missing_from_model.pdb` was not used. The HPC script runs `minim → nvt → npt → md` when `minim2.mdp` is absent.

### Continue an interrupted HPC job

If minim/minim2 finished but NVT failed (e.g. OpenMP thread mismatch), use the updated `*_run.sh` in `hpc/` (per-phase `OMP_NUM_THREADS`) or continue manually from `minim2.gro` with the NVT `grompp` / `mdrun` commands in that script.






####   Examples run in the project  ############
```bash
python run_agenticAIWork.py \
  --goal "I want to study the effect of ATP binding in protein dynamics of these four PDBs p21860.pdb, q8iv63.pdb, q8nb16.pdb, q8wz42.pdb which are available in /pseudo/ directory. Each pdb file has protein + ATP + MG. Please preprocess and setup MD Simulation for 100 ns of all Pdbs with two different cases: 1. Protein only, 2. Protein + ATP + MG therefore total 8 simulations. Once the simulation setups are done please submit the job in HPC. The simulated protein are human pseudokinases and the name of pseudokinase in the uniprotid are p21860: ERBB3, q8iv63: VRK3, q8nb16: MLKL, q8wz42: TITIN. For each system compute: (1) backbone RMSD over time to assess structural stability, (2) per-residue RMSF to identify flexible and rigid regions, Also the RMSF bar plot near active sites (resid 150 to 200) (3) radius of gyration to monitor compactness, (4) center-of-mass distance between the bound ATP ligand and the catalytic pocket (pocket defined as all protein atoms within 5 Å of ATP at frame 0) to track binding-site stability, (5) Dynamic Cross-Correlation Matrix (DCCM) of Cα fluctuations to reveal correlated and anti-correlated residue motions and allosteric communication networks, DCCM diffs in holo and apo form of protein and (6) secondary structure (DSSP) time evolution of whole protein and active sites (resid 150 to 200) which quantify αC-helix and activation-loop structural dynamics. After per-simulation analysis, generate comparative overlay plots and statistical tables across all pseudokinases. For the reporter agent, retrieve relevant literature for each pseudokinase with its given name focusing on activation-loop conformations, allosteric regulation, and dynamics from MD simulations or experimental. Correlate findings results from simulation with literature in the final report." \
  --working-dir pseudo \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim


| `--subtask` | all agents | `preprocess simsetup hpcjob analysis reporter` |



  python run_agenticAIWork.py \
  --goal "I want to study the dynamics of the N-terminal segment of chain B in the two PDBs, dclk3_psma3_in.pdb and dclk3_psma3_less_out.pdb, which are available in the /dclk_PSMA/ directory. Please preprocess and set up 100 ns MD simulations for protein complex provided in both PDBs and submit the jobs on the HPC after setup. In the analysis The main focus should be on chain B from residues 1 to 34 and how this segment interacts with nearby residues in chain A. For each simulation, compute backbone RMSD over time for the whole complex and for chain B residues 1 to 34. Compute per residue RMSF for chain B residues 1 to 34. At frame 0, identify all chain A residues within 10 Å of chain B residues 1 to 34, then compute RMSF for only those chain A residues throughout the trajectory. Also track the center of mass distance and minimum heavy atom distance between chain B residues 1 to 34 and those nearby chain A residues over time to determine whether the N terminal segment remains associated with chain A or moves away. Finally, generate comparative plots and statistical tables for dclk3_psma3_in.pdb versus dclk3_psma3_less_out.pdb, focusing on RMSD, RMSF, contact stability, and distance changes. In the final report, summarize which structure shows greater movement of chain B residues 1 to 34, whether this segment remains close to chain A, and whether nearby chain A residues become more or less flexible during the simulations." \
  --working-dir dclk_PSMA \
  --subtask analysis reporter \
  --simtype multisim


  python run_agenticAIWork.py \
  --goal "Simulation are already done for these uniprot ids: p23458.pdb, p29597.pdb, q7rtn6.pdb, q96c45.pdb. So please do not preprocess or simsetup or hpc. Directly do the analysis of these data. I want specifically RMSF of protein and COM distance of ATP (ligand) from protein for all the simulations. In combined analysis, please compare the RMSF in cross simulations and ligand pocket distance in cross simulaitons. The given uniprotid:protein name are p23458:JAK1, p29597:TYK2, q7rtn6:STRAA and q96c45:ULK4. Calculate the DCCM for JAK1 and TYK2 to compare the dynamics between these two proteins. Please also calculate radius of gyration for JAK1, TYK2 and ULK4 and compare them in plot. In report preparation, please focus on relevant pseudokinase literature of these simulated proteins." \
  --working-dir ./agenticB5R1 \
  --subtask analysis reporter \
  --simtype multisim

 q96c45.pdb, q9bxu1.pdb, q9c0k7.pdb, q9y616.pdb


  python run_agenticAIWork.py \
  --goal "Please run full MD for these uniprot ids: p23458.pdb, p29597.pdb, q7rtn6.pdb, q96c45.pdb, p21860.pdb and p52333.pdb Please setup and run all simulations only for 1 ns. In combined analysis, please compare the RMSF of protein in cross simulations and ligand pocket distance in cross simulaitons only. please do not invent new anlysis. The given uniprotid:protein name are p23458:JAK1, p29597:TYK2, q7rtn6:STRAA, q96c45:ULK4, p21860:ERBB3 and p52333:JAK3. Calculate the DCCM for JAK1 and TYK2 to compare the dynamics between these two proteins. In report preparation, please focus on relevant pseudokinase literature of these simulated proteins." \
  --working-dir ./agenticB5R1_t1 \
  --simtype multisim \
  --allowed-hpc-jobs 4 \
  --hpc-check-interval 3m \
  --resume





  python run_agenticAIWork.py \
  --goal "Please run full MD for these pdb files P34925.pdb, Q6P3W7.pdb, Q6ZS72.pdb, Q86YV5.pdb, Q8IWB6.pdb
Q8IZE3:PACE1
Q96KG9:SCYL1
Q96RU7:TRIB3
Q96RU8:TRIB1
Q9H792:PEAK1
Q9Y4A5.pdb Please setup and run all simulations only for 1 ns. In combined analysis, please compare the RMSF of protein in cross simulations and ligand pocket distance in cross simulaitons only. please do not invent new anlysis. The given uniprotid:protein name are p23458:JAK1, p29597:TYK2, q7rtn6:STRAA, q96c45:ULK4, p21860:ERBB3 and p52333:JAK3. Calculate the DCCM for JAK1 and TYK2 to compare the dynamics between these two proteins. In report preparation, please focus on relevant pseudokinase literature of these simulated proteins." \
  --working-dir ./agenticB5R1_t1 \
  --simtype multisim \
  --allowed-hpc-jobs 4 \
  --hpc-check-interval 3m \
  --resume


```