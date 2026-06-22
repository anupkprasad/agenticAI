# Tools & Dependencies

This document lists the external software, libraries, and services that
AgenticAI relies on. All packages are pinned in `environment.yml`
(conda environment `ollama_env`, Python 3.11).

---

## MD Simulation Engines

| Tool | Version | Role |
|------|---------|------|
| **GROMACS** | 2025.4 | Primary simulation engine — topology (`pdb2gmx`), solvation, ion addition, energy minimisation, equilibration, production MD |
| **AmberTools** | 24.8 | `antechamber` (ligand parameterisation), `tleap`, `pdb4amber`, `cpptraj`, `sander`, `MMPBSA.py` |

### Force Fields & Water Models

- Default force field: **AMBER99SB-ILDN** (`amber99sb-ildn`)
- Default water model: **TIP3P** (`tip3p`)
- Overridable via `--force-field` and `--water-model` CLI flags

---

## Structure Preparation

| Tool | Role |
|------|------|
| **OpenBabel** 3.1.1 | File format conversion (PDB, MOL2, SDF) |
| **RDKit** | Cheminformatics — SMILES handling, ligand processing |
| **PDB2PQR** 3.7.1 | Protonation state assignment |
| **PROPKA** 3.5.1 | pKa estimation for titratable residues (pH 7.0 default) |
| **ACPYPE** 2023.10.27 | Automated AMBER/GROMACS topology generation for ligands |
| **ParmEd** 4.3.0 | Parameter file manipulation and format conversion |
| **PackMol-MemGen** | Membrane system packing |
| **BioPython** | PDB parsing (`Bio.PDB`), structure manipulation, Entrez literature search |

---

## Structure Acquisition (new)

These modules enable starting from a UniProt accession with no local PDB file.

| Module | Path | Role |
|--------|------|------|
| **Request parser** | `src/preprocess/structure_request_parser.py` | Extracts UniProt ID, domain label, residue ranges from natural language |
| **AlphaFold source** | `src/preprocess/structure_sources/alphafold.py` | Downloads predicted structure from AlphaFold API (default) |
| **RCSB source** | `src/preprocess/structure_sources/rcsb.py` | Downloads experimental structure from RCSB PDB (fallback) |
| **Source registry** | `src/preprocess/structure_sources/registry.py` | Priority-ordered pluggable download backends |
| **UniProt domain source** | `src/preprocess/domain_sources/uniprot.py` | Queries UniProt REST API for Domain/Region feature annotations |
| **Domain registry** | `src/preprocess/domain_sources/registry.py` | `lookup_domain_range()` with offline fallback table |
| **Domain extractor** | `src/preprocess/domain_extractor.py` | Trims PDB to a residue span (BioPython + MDAnalysis) |
| **Acquire structure tool** | `src/preprocess/acquire_structure_tool.py` | End-to-end: download → domain trim → validate |
| **Domain lookup tool** | `src/preprocess/domain_lookup_tool.py` | `lookup_domain_range_tool` (LangChain `@tool`) for the Preprocessing agent |
| **Structure validator** | `src/preprocess/structure_validator.py` | Missing residue check, broken backbone (Cα–Cα > 4.5 Å), component availability |
| **Structure downloader** | `src/preprocess/structure_downloader.py` | `download_structure` tool wrapping AlphaFold + RCSB backends |

### External APIs used for structure acquisition

| API | Purpose | Documentation |
|-----|---------|---------------|
| AlphaFold EBI API | Fetch predicted PDB by UniProt accession | `https://alphafold.ebi.ac.uk/api/prediction/{accession}` |
| RCSB PDB REST API | Fetch experimental PDB by entry ID | `https://files.rcsb.org/download/{id}.pdb` |
| UniProt REST API | Domain / Region feature annotations | `https://rest.uniprot.org/uniprotkb/{accession}` |

---

## Trajectory Analysis

Primary library: **MDAnalysis v2.10.0**

### Per-simulation tools (`agentic/analysis/tools.py`)

| Tool | Observable |
|------|------------|
| `calculate_rmsd` | Backbone Cα RMSD relative to reference |
| `calculate_rmsf` | Per-residue root-mean-square fluctuation |
| `calculate_radius_of_gyration` | Global compactness (Rg) |
| `calculate_sasa` | Solvent-accessible surface area |
| `analyze_energy` | Potential energy and temperature from `.edr` |
| `analyze_secondary_structure` | DSSP time evolution (whole + user-defined segment) |
| `calculate_com_distance` | Centre-of-mass distance between two atom groups |
| `calculate_ligand_pocket_distance` | ATP–pocket distance (pocket = atoms within 5 Å of ligand at frame 0) |
| `calculate_dccm` | Dynamic cross-correlation matrix of Cα fluctuations |
| `plot_dccm_difference` | Element-wise DCCM difference between two simulations (apo–holo) |
| `plot_md_data` | Single-trace time-series plot |
| `plot_md_multipanel` | Multi-panel figure |
| `plot_combined_data` | Overlay plot for multiple datasets |
| `wrap_trajectory` | PBC wrapping with `gmx trjconv` |
| `extract_trajectory_metrics` | Bulk metric extraction to CSV |

### Combined (multi-simulation) tools

| Tool | Function |
|------|----------|
| `collect_metric_files` | Gather matching metric files across simulation directories |
| `plot_combined_overlay` | Multi-trace overlay plot (RMSD, RMSF, Rg, energy) with legend |
| `compute_comparison_table` | Statistical summary JSON (mean, std, min, max per metric per simulation) |
| `run_combined_analysis` | Full combined pipeline entry point |
| `run_combined_dccm_analysis` | DCCM panels for all simulations |
| `run_combined_dccm_difference` | Cross-simulation DCCM difference heatmap |
| `run_combined_rmsf_segment_analysis` | RMSF bar chart for user-defined residue window |
| `run_combined_com_distance_analysis` | COM distance overlay across simulations |
| `plot_combined_rmsf_segment_bars` | Stacked segment RMSF bar chart |

### Additional analysis libraries

| Tool | Version | Role |
|------|---------|------|
| **PyTraj** | 2.0.6 | AMBER cpptraj wrapper for trajectory analysis |
| **scikit-learn** | 1.6.1 | Cross-simulation PCA on Cα coordinates |
| **Matplotlib** | 3.10.8 | Publication-quality 2D plots |
| **Seaborn** | — | Statistical plot styling |

---

## AI / LLM Framework

| Tool | Version | Role |
|------|---------|------|
| **LangGraph** | 1.0.7 | StateGraph-based workflow orchestration — nodes, edges, conditional routing |
| **LangChain** | 1.2.8 | Chain and prompt utilities; `@tool` decorator for agent tools |
| **Ollama** | 0.6.1 | Local LLM inference server; default model `gpt-oss:20b` |
| **LangSmith** | — | Optional tracing / observability |

### LLM integration pattern

```
User Goal
  │
  v
Supervisor: structured_prompt (single enrichment LLM call)
  │
  v
Planner: tools + knowledge + goal ──► Ollama /api/generate
                                              │
                                              v
                                      Execution plan
                                   (per-agent instructions)
  │
  v
Field agents: each reads its *_instructions field
              makes targeted LLM calls for tool selection
  │
  v
Reporter: literature retrieval + LLM narrative
```

Fallback: when LLM is unreachable, heuristic routing and rule-based report synthesis activate automatically.

---

## Visualisation & Reporting

| Tool | Role |
|------|------|
| **Matplotlib** 3.10.8 | RMSD, RMSF, Rg, energy, DCCM, COM distance plots |
| **Seaborn** | Statistical styling for overlay and comparison plots |
| **3Dmol.js** (CDN) | Interactive 3D molecular viewer embedded in HTML report |

### HTML Report Features

- Task description from enriched / master prompt
- Embedded analysis figures and combined overlay plots
- DCCM heatmaps and apo–holo DCCM difference panel
- LLM-generated scientific narrative (rule-based fallback)
- Literature references with PubMed / bioRxiv / UniProt source badges
- 3D structure viewer: representations, colour schemes, surface, sequence bar,
  trajectory snapshots at diagnostic frames, PNG export

---

## HPC & Remote Execution

| Tool | Version | Role |
|------|---------|------|
| **SLURM** | — | HPC job scheduler |
| **Paramiko** | 4.0.0 | SSH/SFTP for remote HPC execution |
| **Singularity** | — | Container runtime for reproducible environments on HPC |

### HPC script naming convention

```
{job_name}_run.sh   ← correct (derived from simulation label)
slurm_job.sh        ← incorrect (LLM-hallucinated; ignored by HPC agent)
```

---

## Literature Search APIs

| Source | API | Purpose |
|--------|-----|---------|
| **PubMed** | NCBI E-utilities (BioPython Entrez) | Peer-reviewed MD/protein literature |
| **bioRxiv** | Europe PMC REST (`SRC:PPR` filter) | Preprints |
| **UniProt** | UniProt REST API | Reviewed protein function, domain annotations |

Results are deduplicated by PMID and DOI, capped at 15 references per report.

---

## Run Summary Utility

| Module | Path | Role |
|--------|------|------|
| `run_summary.py` | `src/utils/run_summary.py` | Build + write `run_summary.md` and `run_summary.json` at workflow exit |

Functions:
- `build_run_summary(final_state, working_dir, goal, pdb_list, config)` → summary dict
- `write_run_summary(working_dir, summary)` → writes JSON + Markdown
- `format_run_summary_terminal(summary)` → terminal-printable block

---

## Testing & Development

| Tool | Role |
|------|------|
| **pytest** | Unit and integration testing |
| **invoke** | Task runner |
| **PyYAML** | Configuration file parsing |
| **tqdm** | Progress bars |
