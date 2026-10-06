# MD Workflow Execution Report

**Generated:** 2026-10-06 11:40:34  
**Status:** SUCCESS

---

## User Prompt

> For the apo VRK3 system (label q8iv63, source q8iv63.pdb, dir /home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63), preprocess, set up a 1‑ns MD with AMBER99SB-ILDN/TIP3P at 310 K/1 bar, submit to HPC, then analyze backbone RMSD, per‑residue RMSF (150–200), radius of gyration, Cα DCCM, DSSP time evolution, and produce overlay plots. The reporter will gather VRK3 literature on activation‑loop dynamics and allosteric regulation. Case requirement: case_id=protein_only Protein only (apo) Preprocess and set up MD simulations for 1 ns with AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, 0.15 M NaCl for all four PDBs (p21860.pdb, q8iv63.pdb, q8nb16.pdb, q8wz42.pdb). Use protein only: exclude ligand and crystallographic ions from the source PDB.

Original study goal (applies to every system):
I want to study the effect of ATP binding on protein dynamics for these four
PDBs — p21860.pdb, q8iv63.pdb, q8nb16.pdb, and q8wz42.pdb — which are available
in this working directory. Each PDB has protein + ATP + Mg.

Please preprocess and set up MD simulations for 1 ns for all PDBs with two
component cases per structure:
  1. Protein only (apo)
  2. Protein + ATP + Mg (holo)
for a total of eight simulations. Once setups are done, submit the jobs to HPC.

The proteins are human pseudokinases (UniProt id : name):
  p21860: ERBB3, q8iv63: VRK3, q8nb16: MLKL, q8wz42: TITIN.

Force field AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, 0.15 M NaCl.

For each system compute:
  (1) backbone RMSD over time,
  (2) per-residue RMSF (and an RMSF bar plot near the active-site region,
      residues 150–200 when present),
  (3) radius of gyration,
  (4) COM distance between bound ATP and the catalytic pocket (pocket =
      protein atoms within 5 Å of ATP at frame 0) for holo systems,
  (5) Cα DCCM, including apo vs holo DCCM differences where both cases exist,
  (6) DSSP time evolution for the whole protein and the active-site region
      (residues 150–200 when present).

After per-simulation analysis, generate comparative overlay plots and
statistical tables across all systems. In the reporter, retrieve relevant
literature for each named protein focusing on activation-loop conformations,
allosteric regulation, and MD or experimental dynamics, and correlate the
simulation findings with that literature in the final report.

## Enriched Prompt

**Rephrased Goal for the Workflow Agents (analysis → reporter)**  
1. Perform per‑trajectory analysis on the already‑generated 1 ns trajectories for the apo (protein‑only) versions of p21860.pdb, q8iv63.pdb, q8nb16.pdb, and q8wz42.pdb: compute backbone RMSD, per‑residue RMSF (including a dedicated bar plot for residues 150–200 when present), radius of gyration, Cα dynamic cross‑correlation matrices, and DSSP secondary‑structure time evolution (whole protein and residues 150–200).  
2. Generate comparative overlay plots and statistical tables summarizing these metrics across the four systems.  
3. Produce a literature report for each protein (ERBB3, VRK3, MLKL, TITIN) that focuses on activation‑loop conformations and allosteric regulation, and correlate the simulation findings with the retrieved studies.  
4. All analyses should use the existing trajectories only; no new preprocessing, simulation setup, or HPC submission steps are required.

## Execution Plan

**Detailed Natural Language Execution Plan**

Agent sequence: analysis_agent

**Goal**  
Perform a complete per‑trajectory dynamical analysis of the 1 ns apo simulation of *q8iv63* (ERBB3).  
The analysis must compute the following metrics and generate the standard output files in the
`/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63/analysis/` directory:

| Metric | Tool | Output files |
|--------|------|--------------|
| Backbone RMSD | `calculate_rmsd` | `rmsd.dat`, `rmsd.png` |
| Per‑residue RMSF (whole protein) | `calculate_rmsf` | `rmsf.dat`, `rmsf.png` |
| Per‑residue RMSF (residues 150–200, if present) | `calculate_rmsf` | `rmsf_150to200.dat`, `rmsf_150to200.png` |
| Radius of gyration | `calculate_radius_of_gyration` | `gyration.dat`, `gyration.png` |
| Cα dynamic cross‑correlation matrix | `calculate_dccm` | `dccm.dat`, `dccm_heatmap.png` |
| DSSP secondary‑structure evolution (whole protein) | `analyze_secondary_structure` | `dssp.dat`, `dssp.png` |
| DSSP secondary‑structure evolution (residues 150–200, if present) | `analyze_secondary_structure` | `dssp_150to200.dat`, `dssp_150to200.png` |

No cross‑simulation overlay, statistical tables, or literature synthesis is performed at this stage; those steps are reserved for the later Reporter phase.

---

### Execution Sequence (to be carried out by the **Analysis Agent**)

1. **File discovery**  
   The agent automatically locates the topology (`md.gro`) and trajectory (`md.xtc`) in the `hpc/` subdirectory.  
   It creates the output directory `analysis/` if it does not already exist.

2. **Backbone RMSD**  
   *Tool:* `calculate_rmsd`  
   *Parameters:*  
   - `topology_file` = `hpc/md.gro`  
   - `trajectory_file` = `hpc/md.xtc`  
   - `selection` = `"backbone"`  
   - `output_file` = `analysis/rmsd.dat` (time‑series)  
   - `plot_file` = `analysis/rmsd.png` (line plot)  

3. **Per‑residue RMSF – whole protein**  
   *Tool:* `calculate_rmsf`  
   *Parameters:*  
   - `topology_file` = `hpc/md.gro`  
   - `trajectory_file` = `hpc/md.xtc`  
   - `selection` = `"protein"`  
   - `output_file` = `analysis/rmsf.dat`  
   - `plot_file` = `analysis/rmsf.png` (bar plot)  

4. **Per‑residue RMSF – residues 150–200**  
   *Tool:* `calculate_rmsf`  
   *Parameters:*  
   - `topology_file` = `hpc/md.gro`  
   - `trajectory_file` = `hpc/md.xtc`  
   - `selection` = `"resid 150-200"`  
   - `output_file` = `analysis/rmsf_150to200.dat`  
   - `plot_file` = `analysis/rmsf_150to200.png`  

   *Conditional logic:*  
   The agent first checks whether residues 150–200 exist in the topology.  
   If the selection yields no atoms, the step is skipped and a log entry is written.

5. **Radius of gyration**  
   *Tool:* `calculate_radius_of_gyration`  
   *Parameters:*  
   - `topology_file` = `hpc/md.gro`  
   - `trajectory_file` = `hpc/md.xtc`  
   - `output_file` = `analysis/gyration.dat`  
   - `plot_file` = `analysis/gyration.png`  

6. **Cα Dynamic Cross‑Correlation Matrix**  
   *Tool:* `calculate_dccm`  
   *Parameters:*  
   - `topology_file` = `hpc/md.gro`  
  ...

## Key Artifacts

- Cleaned PDB: `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63/simsetup/protein.pdb`
- Topology: `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63/hpc/md.tpr`
- Coordinates: `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63/simsetup/system.gro`
- MDP files: `ions`, `minim`, `nvt`, `npt`, `md`

## Summary

# MD Workflow Completion Report  
**Project**: Apo‑ and Holo‑MD of human pseudokinases (p21860, q8iv63, q8nb16, q8wz42)  
**Case ID**: 4 × 2 = 8 simulations (Protein‑only = apo; Protein + ATP + Mg²⁺ = holo)  
**Force Field**: AMBER99SB‑ILDN / TIP3P  
**Simulation Conditions**: 310 K, 1 bar, 0.15 M NaCl, 1 ns, periodic boundary conditions  
**Primary Goal**: Generate backbone RMSD, per‑residue RMSF (150–200), radius of gyration, COM‑distance (holo), Cα DCCM, DSSP time evolution, overlay plots, and contextualize findings with literature on activation‑loop dynamics and allostery.

---

## 1. Workflow Status  
| Stage | Result |
|-------|--------|
| Pre‑processing (protein‑only, ligand removal) | **Success** – Cleaned PDB (`/home/akp66103/.../q8iv63/simsetup/protein.pdb`) |
| Topology & System Generation | **Success** – TPR (`/home/akp66103/.../q8iv63/hpc/md.tpr`) & GRO (`/home/akp66103/.../q8iv63/simsetup/system.gro`) |
| MDP File Creation | **Partial** – mdp files list truncated (`ions.mdp`, `min`, …) |
| Job Submission | **Partial** – Job submitted for the apo q8iv63 run; other seven simulations not yet queued |
| Analysis | **Partial** – Backbone RMSD calculated (`mean = 1.16 Å`, `std = 0.40 Å`). All other metrics (RMSF, Rg, COM‑dist, DCCM, DSSP) not yet executed |
| Literature Review | **Not yet** – Literature search for ERBB3, VRK3, MLKL, TITIN pending |

**Overall status**: **Partial – Work in progress for 1 ns apo q8iv63. Remaining simulations and analyses pending.**

---

## 2. Agents Executed & Results  

| Agent | Purpose | Output | Notes |
|-------|---------|--------|-------|
| **ProteinPreprocessor** | Remove non‑protein atoms (ligands, waters, ions) | Cleaned PDB (`protein.pdb`) | Successful |
| **TopologyGenerator** | Generate GROMACS topology using AMBER99SB‑ILDN | TPR file (`md.tpr`) | Successful |
| **SystemBuilder** | Solvate, add ions, create GRO | System GRO (`system.gro`) | Successful |
| **MDPWriter** | Create mdp files for minimization, equilibration, production | `ions.mdp`, `min.mdp` (incomplete) | Incomplete list |
| **JobSubmitter** | Submit to HPC queue | Submission log (partially present) | Only apo q8iv63 submitted |
| **AnalysisRunner** | Compute RMSD, RMSF, Rg, COM‑dist, DCCM, DSSP | RMSD table (partial) | Others not run |
| **LiteratureRetriever** | Search PubMed/Google Scholar | None yet | Awaiting execution |
| **PlotGenerator** | Create overlay plots | None yet | Awaiting data |

---

## 3. Files Generated (so far)

| File | Path | Description |
|------|------|-------------|
| `protein.pdb` | `/home/akp66103/.../q8iv63/simsetup/protein.pdb` | Protein‑only PDB, ligands/ions removed |
| `md.tpr` | `/home/akp66103/.../q8iv63/hpc/md.tpr` | Topology & simulation parameters (AMBER99SB‑ILDN, TIP3P) |
| `system.gro` | `/home/akp66103/.../q8iv63/simsetup/system.gro` | Solvated system with 0.15 M NaCl |
| `ions.mdp` | `/home/akp66103/.../q8iv63/simsetup/ions.mdp` | MDP for ion placement (truncated list) |
| `analysis_results.json` (partial) | In-memory | RMSD stats (`mean = 1.16 Å`, `std = 0.40 Å`) |

*Note*: The `mdp_files` entry in `final_outputs` is incomplete; full set of mdp files (minimization, NVT, NPT, production) should be listed.

---

## 4. Issues Encountered

| Issue | Severity | Impact | Current Mitigation |
|-------|----------|--------|--------------------|
| **Partial mdp generation** | Low | Incomplete job scripts | Verify mdp templates; regenerate missing sections |
| **Only one simulation submitted** | Medium | Delays comparative analysis | Queue remaining 7 jobs ASAP |
| **Incomplete analysis output** | High | Cannot produce final report | Run remaining analyses after simulation completion |
| **No literature review yet** | Medium | Context missing for final correlation | Initiate search with specified keywords |
| **Missing per‑residue RMSF/Rg/COM‑dist** | High | Key metrics not available | Run analysis scripts on trajectory |
| **Holo cases not processed** | High | Core objective incomplete | Preprocess holo PDBs, add ATP & Mg²⁺, generate topology |

---

## 5. Next Steps & Recommendations

1. **Complete MDP Setup**  
   * Ensure `min.mdp`, `nvt.mdp`, `npt.mdp`, and `md.mdp` are fully generated for all eight simulations.  
   * Validate parameter files with `gmx check`.

2. **Preprocess Holo Structures**  
   * For each PDB, retain ATP and Mg²⁺, remove crystallographic ions not part of the binding site.  
   * Generate topology for ligands using `antechamber` or `parmchk2`, then `tleap`.

3. **Submit Remaining Jobs**  
   * Queue the seven pending simulations (3 apo + 4 holo) on HPC.  
   * Use a job array or a workflow manager (e.g., `snakemake`, `ruffus`) to manage dependencies.

4. **Automate Analysis Pipeline**  
   * After each trajectory finishes, run the full analysis script:  
     - Backbone RMSD (reference: first frame or crystal structure).  
     - Per‑residue RMSF (residues 150–200 for proteins with that segment).  
     - Radius of gyration (global).  
     - COM distance (holo only).  
     - Cα DCCM (compare apo vs holo).  
     - DSSP time series (global & active‑site region).  
   * Store results in CSV/JSON and generate plots (`matplotlib`, `seaborn`).

5. **Generate Comparative Plots & Tables**  
   * Overlay RMSD curves across all eight systems.  
   * Side‑by‑side RMSF bar plots (highlight residues 150–200).  
   * Heatmaps for DCCM differences.  
   * Table of average Rg, COM‑dist, etc.

6. **Literature Retrieval & Integration**  
   * Query PubMed/Google Scholar for each protein with keywords: “activation loop dynamics”, “allosteric regulation”, “MD simulation”, “pseudokinase”, “ATP binding”.  
   * Summarize findings in a table (protein, key residues, known conformational states, experimental techniques).  
   * Compare simulation metrics to literature reports; discuss congruence or divergence.

7. **Final Report Draft**  
   * Executive summary, methodology, results (tables/figures), discussion linking simulation and literature, conclusion.  
   * Appendices: full mdp files, analysis scripts, raw data references.

8. **Quality Checks**  
   * Verify energy conservation and pressure/temperature stability in production runs.  
   * Check for periodic artefacts or trajectory artefacts (e.g., jump in RMSD).

9. **Backup & Version Control**  
   * Commit all scripts, mdp files, and analysis outputs to a Git repo.  
   * Archive raw trajectories if storage permits; otherwise keep compressed versions.

---

### Summary

- **Pre‑processing** completed for q8iv63 apo.  
- **Simulation setup** successful for one run; others pending.  
- **Analysis** performed only for RMSD of this run.  
- **Literature review** not started.  

Immediate focus should be on completing the mdp files, processing the holo cases, submitting all jobs, and running the full analysis pipeline. Once all metrics are available, we can produce the comparative plots and integrate literature insights to finalize the report.
