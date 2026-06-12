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

**Full usage guide:** [docs/TUTORIAL.md](docs/TUTORIAL.md)

---

## Key Features

- **Natural-language goals** — describe what you want; agents build a concrete plan
- **UniProt / AlphaFold integration** — start from an accession without a local PDB
- **Multi-simulation mode** — compare proteins or component cases (apo vs holo) in one run
- **Holo feasibility guard** — skips holo cases when ligands are missing (e.g. AlphaFold)
- **Phosphorylated proteins** — SEP/TPO/PTR stay in the protein chain; mapped for
  CHARMM36 (SP2/THP/TP2), not parameterized as separate ligands
- **Supervisor → Planner → Agents** — validated routing and tool-based execution
- **Resume / retry** — re-run failed multi-sim jobs without redoing successes
- **Audit trail** — `agent_conversation.log`, `run_summary.md`, execution plans

---

## Prerequisites

```bash
conda env create -f environment.yml
conda activate ollama_env
```

Optional (LLM mode): Ollama or compatible endpoint:

```bash
curl -s http://127.0.0.1:11434/api/tags
```

**GROMACS** is included in the conda environment. For phosphorylated proteins with
CHARMM36, install `charmm36-jul2022.ff` (see [Force fields](#force-fields)).

---

## Quick Start

### Single simulation from a local PDB

```bash
python run_agenticAIWork.py \
  --goal "Preprocess and setup MD for my_protein.pdb for 50 ns, then submit to HPC" \
  --working-dir /work/run1 \
  --subtask preprocess simsetup hpcjob \
  --use-llm --no-human-loop
```

### UniProt accession (download + domain extraction)

```bash
python run_agenticAIWork.py \
  --goal "Study ATP binding of UniProt P21860 (ERBB3). Download AlphaFold PDB,
          extract kinase domain, run 1 ns MD for protein-only and protein+ATP+MG.
          Submit to HPC." \
  --working-dir /work/erbb3 \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim \
  --use-llm --no-human-loop
```

### Multi-protein comparative study

```bash
python run_agenticAIWork.py \
  --goal "Run 100 ns MD for each pseudokinase and submit to HPC.
          Names: p21860=ERBB3, q8iv63=VRK3, q8nb16=MLKL, q8wz42=TITIN." \
  --pdb-list p21860.pdb q8iv63.pdb q8nb16.pdb q8wz42.pdb \
  --working-dir /work/pseudo \
  --subtask preprocess simsetup hpcjob \
  --simtype multisim \
  --use-llm --no-human-loop
```

### Analysis-only on completed trajectories

```bash
python run_agenticAIWork.py \
  --goal "Compute RMSD, RMSF, Rg, DCCM, DSSP and generate the report." \
  --working-dir /work/run1 \
  --subtask analysis reporter \
  --use-llm --no-human-loop
```

More examples (resume, component cases, parameter overrides): [docs/TUTORIAL.md](docs/TUTORIAL.md)

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
| `--use-llm` | off | Enable LLM routing and planning |
| `--llm-model` | `gpt-oss:20b` | Model name |
| `--llm-base-url` | `http://localhost:11434` | LLM API base URL |
| `--no-human-loop` | off | Skip human approval checkpoints |
| `--force-field` | `amber99sb-ildn` | GROMACS force field (e.g. `charmm36-jul2022`) |
| `--water-model` | `tip3p` | Water model |
| `--max-concurrent` | `4` | Max concurrent sims in multi-sim mode |
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
/work/pseudo/
  p21860/
    preprocess/       # protein.pdb, protein_h.pdb, ...
    simsetup/         # topol.top, *.gro, *.mdp
    hpc/              # SLURM script, trajectories
    analysis/         # RMSD, RMSF, DCCM plots
    reporter/         # report.html
    agent_conversation.log
  p21860_ATP_MG/      # or skipped with reason in run_summary
  analysis/           # combined overlay plots
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
docs/
  TUTORIAL.md              # End-to-end usage guide
  ARCHITECTURE.md          # System design
  PROJECT.md               # Extended project overview
  TOOLS.md                 # Tool catalogue
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/TUTORIAL.md](docs/TUTORIAL.md) | Step-by-step workflows and troubleshooting |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | LangGraph pipeline and multi-sim design |
| [docs/PROJECT.md](docs/PROJECT.md) | Extended overview and conventions |
| [docs/TOOLS.md](docs/TOOLS.md) | Available agent tools |
| [docs/CONVENTIONS.md](docs/CONVENTIONS.md) | Naming and file conventions |

---

## Development

```bash
# Run without LLM (heuristic routing)
python run_agenticAIWork.py --goal "..." --no-human-loop

# With local Ollama
python run_agenticAIWork.py --goal "..." --use-llm --llm-base-url http://127.0.0.1:11434
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
  --use-llm --no-human-loop \
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

