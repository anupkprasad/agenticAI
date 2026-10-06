# MD Workflow Execution Report

**Generated:** 2026-10-06 11:40:53  
**Status:** SUCCESS

---

## User Prompt

> For the holo ERBB3 system (label p21860_ATP_MG, source p21860.pdb, dir /home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG), preprocess, set up a 1‑ns MD with AMBER99SB-ILDN/TIP3P at 310 K/1 bar, submit to HPC, then analyze backbone RMSD, per‑residue RMSF (150–200), radius of gyration, COM distance between ATP and the catalytic pocket (atoms within 5 Å of ATP at frame 0), Cα DCCM, DSSP time evolution, and produce overlay plots. The reporter will retrieve ERBB3 literature on ATP binding and activation‑loop dynamics. Case requirement: case_id=protein_with_ligand Protein + ATP + Mg (holo) Preprocess and set up MD simulations for 1 ns with AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, 0.15 M NaCl for all four PDBs, including ATP and Mg in the binding site. Include the ligand and crystallographic Mg/ions from the source PDB.

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

**Rephrased Goal for the Analysis & Reporter Workflow**

1. **Analysis**  
   - For the eight existing 1‑ns trajectories (apo and holo for each of ERBB3, VRK3, MLKL, and TITIN) generated under AMBER99SB-ILDN/TIP3P at 310 K/1 bar with 0.15 M NaCl, compute:  
     • Backbone RMSD over time.  
     • Per‑residue RMSF, with a dedicated bar plot of residues 150–200 (when present).  
     • Radius of gyration.  
     • For holo systems only, the COM distance between ATP and the catalytic pocket (protein atoms within 5 Å of ATP in frame 0).  
     • Cα distance‑correlation maps (DCCM); calculate difference maps (apo – holo) where both cases exist.  
     • DSSP time evolution for the whole protein and for residues 150–200.  
   - Produce overlay plots (e.g., RMSD, RMSF, Rg, COM distance, DCCM) and statistical tables summarizing all eight simulations.

2. **Reporter**  
   - Retrieve and summarize literature on ATP binding, activation‑loop conformations, and allosteric regulation for ERBB3, VRK3, MLKL, and TITIN.  
   - Correlate the simulation findings with the literature, highlighting agreements or novel insights.  

*Constraints:* Only perform the above analyses; do not preprocess, solvate, or run new simulations. Use the default physiological conditions already represented in the trajectories.

## Execution Plan

**Detailed Natural Language Execution Plan**

Agent sequence: analysis_agent

**Goal**  
Perform all requested per‑simulation analyses on the single trajectory located in  
`/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/hpc/`.  
The results will be written to the per‑simulation analysis folder  
`/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/analysis/`.  
No cross‑simulation overlay, statistical tables, or combined plots are produced at this stage; those will be assembled later by the higher‑level workflow.

---

### 1. Analysis Agent – Execution Sequence

| Step | Tool | Purpose | Key Parameters | Output Files |
|------|------|---------|----------------|--------------|
| 1 | **calculate_rmsd** | Backbone RMSD of the protein over time. | `topology_file` = md.gro, `trajectory_file` = md.xtc | `rmsd.dat`, `rmsd.png` |
| 2 | **calculate_rmsf** | Per‑residue RMSF of the protein. | Same topology/trajectory | `rmsf.dat`, `rmsf.png` |
| 3 | **calculate_radius_of_gyration** | Radius of gyration of the whole protein. | Same topology/trajectory | `gyration.dat`, `gyration.png` |
| 4 | **calculate_dccm** | Full‑protein Dynamic Cross‑Correlation Matrix. | Same topology/trajectory | `dccm.dat`, `dccm_heatmap.png` |
| 5 | **analyze_secondary_structure** | DSSP assignment for every residue at every frame. | Same topology/trajectory | `dssp.dat`, `dssp.png` |
| 6 | **calculate_ligand_pocket_distance** *(only if holo)* | COM distance between ATP and the catalytic pocket (atoms within 5 Å of ATP in frame 0). | `ligand_selection="resname ATP"`, `cutoff=5.0` | `ligand_pocket_distance.csv`, `ligand_pocket_distance.png` |

> **Why these tools?**  
> Each metric requested in the user goal is directly supported by a registered tool.  
> The metric‑to‑tool map confirms that `rmsd`, `rmsf`, `rg`, `dccm`, `dssp`, and `com` are covered.  
> No custom tool creation is required.

---

### 2. Post‑processing & Qualified Outputs

After the raw data files are produced, the Analysis Agent will perform lightweight post‑processing to generate the requested residue‑range plots and data files.

| Post‑process | What is extracted | Output |
|--------------|-------------------|--------|
| **Residue‑range RMSF (150–200)** | From `rmsf.dat`, select rows where residue number ∈ [150,200]. | `rmsf_150-200.dat` (time series) and `rmsf_150-200.png` (bar plot) |
| **Residue‑range DSSP (150–200)** | From `dssp.dat`, select the same residue window. | `dssp_150-200.dat` (time series) and `dssp_150-200.png` (heat‑map or line plot) |
| **COM distance plot** | Already produced by `calculate_ligand_pocket_distance`. | `ligand_pocket_distance.png` (time series) |

The Analysis Agent will use Python’s `pandas` and `matplotlib` libraries to read the `.dat`/`.csv` files, filter the residue range, and generate the bar/line plots. The plots will be saved in the same analysis directory with the exact filenames specified in the “Standard per‑simulation output filenames” table.

---

### 3. File Organization

All output files will b...

## Key Artifacts

- Cleaned PDB: `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/simsetup/protein.pdb`
- Topology: `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/hpc/md.tpr`
- Coordinates: `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/simsetup/system.gro`
- MDP files: `ions`, `minim`, `nvt`, `npt`, `md`

## Summary

# MD Workflow Completion Report  
**Project:** ERBB3 / Human Pseudokinase MD Study  
**Scope:** Eight 1‑ns production runs (apo & holo for p21860, q8iv63, q8nb16, q8wz42) → analysis → comparative overlay & literature integration.  

| Item | Details |
|------|---------|
| **Workflow Status** | **Partial** – one of eight simulations (p21860 holo) is fully pre‑processed, submitted, and partially analyzed. The remaining 7 runs are pending. |
| **Agents Executed** | None listed in the workflow meta‑data (agents_used = []), implying the steps were executed directly by the system’s internal scripts. |
| **Key Results** | *p21860 holo* (ERBB3 ATP/Mg²⁺) – successful pre‑processing, topology generation, trajectory file produced. Preliminary RMSD analysis indicates a stable backbone (mean ≈ 1.29 Å, σ ≈ 0.43 Å). |
| **Generated Files** | <br>• **Cleaned PDB** – `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/simsetup/protein.pdb`<br>• **Topology** – `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/hpc/md.tpr`<br>• **Coordinates** – `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/simsetup/system.gro`<br>• **Mdp files** – ions‑mdp reference: `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/simsetup/ions.mdp`<br>• **Analysis** – `analysis_results` (JSON) containing RMSD metrics. |
| **Issues Encountered** | None reported (0 errors, 0 warnings). However, workflow completeness is incomplete – only one of eight simulations finished. |
| **Next Steps / Recommendations** | 1. **Complete Setup for Remaining Systems**<br>   * Run pre‑processing for: <br>     – p21860 apo<br>     – q8iv63 holo & apo<br>     – q8nb16 holo & apo<br>     – q8wz42 holo & apo<br>   * Verify ligand & ion positions, add missing hydrogens, create topology with AMBER99SB‑ILDN/TIP3P, set 310 K, 1 bar, 0.15 M NaCl. |
> 2. **HPC Submission** – Batch submit all 8 MD jobs (1 ns each). Monitor queue status and resource usage; ensure proper checkpointing. |
> 3. **Post‑Processing & Analysis**<br>   * For each trajectory: compute backbone RMSD, per‑residue RMSF (highlight 150–200 if present), radius of gyration, COM distance (holo only), Cα DCCM, DSSP time‑series. <br>   * Generate per‑system plots (RMSD curves, RMSF bar graphs, Rg vs time, COM vs time, DCCM heatmaps). |
> 4. **Comparative Overlay & Statistics**<br>   * Overlay backbone RMSD/Rg of apo vs holo across all proteins. <br>   * Create statistical tables (mean/σ of RMSF, COM distances, DCCM difference metrics). <br>   * Apply clustering or PCA to identify common dynamic modes. |
> 5. **Literature Integration**<br>   * Retrieve recent studies (2018‑2024) on ERBB3, VRK3, MLKL, TITIN activation‑loop dynamics, ATP‑binding conformations, and allosteric regulation. <br>   * Summarize key findings (e.g., known crystal structures, MD insights, functional assays). <br>   * Correlate simulation observations (e.g., increased RMSF in the activation loop upon ATP binding) with experimental evidence. |
> 6. **Documentation & Reporting**<br>   * Draft a comprehensive report (≈ 15 pages) with methodology, results, figures, tables, and literature discussion. <br>   * Include appendices: raw data, command logs, and scripts. |
> 7. **Optional Enhancements**<br>   * Extend production runs to 5–10 ns to improve sampling. <br>   * Perform free‑energy calculations (e.g., MM‑GBSA) for ATP binding affinity comparison. |
> 8. **Quality Assurance**<br>   * Verify that each trajectory reaches the intended length (1 ns). <br>   * Cross‑check that force field parameters for ATP/Mg²⁺ are correctly assigned. |

---

## Summary of Completed Deliverables (p21860 holo)

| Deliverable | Status | Notes |
|-------------|--------|-------|
| Cleaned PDB | ✅ | Hydrogens added, waters retained. |
| Topology & Coordinates | ✅ | MD‑input ready. |
| MD run submitted | ✅ | Job queued on HPC cluster. |
| RMSD analysis | ✅ | Mean 1.29 Å, σ 0.43 Å. |
| Other analyses | ❌ | Not yet performed. |

---

## Action Items (Team)

| Task | Owner | Deadline |
|------|-------|----------|
| Complete pre‑processing for all remaining PDBs | MD Lead | Day + 2 |
| Submit all eight jobs | HPC Admin | Day + 3 |
| Generate all analysis outputs | Analyst | Day + 10 |
| Compile overlay figures & tables | Data Viz | Day + 12 |
| Literature search & synthesis | Bioinformatics | Day + 15 |
| Draft final report | Lead Writer | Day + 20 |

---

**Prepared by:**  
[Your Name] – Computational Biophysicist  
[Lab / Institution]  
[Date: 2026‑10‑06]
