# Planner Execution Plan

**Generated:** 2026-10-06 11:42:56
**Phase:** single

## Overview

**Title:** Detailed Natural Language Execution Plan
**Agent sequence:** analysis_agent
**Subtask:** analysis_only

## Full Plan

**Goal**  
Perform a complete, per‑simulation analysis of the supplied MD trajectory for the protein *q8nb16_ATP_MG*.  
The analysis will generate all metrics requested in the user goal—backbone RMSD, per‑residue RMSF (with a focused bar plot for residues 150–200), radius of gyration, ligand‑pocket COM distance (for holo systems), full‑protein Cα DCCM, and DSSP time evolution (full protein and residues 150–200).  
All results will be written to the simulation’s `analysis/` directory using the standard basenames so that a later, cross‑simulation overlay step can collect them.

---

### 1.  Analysis Agent Workflow

The **Analysis Agent** will orchestrate the following sequence of tool invocations.  
Each tool is called with the trajectory and topology that the agent automatically discovers in the `hpc/` sub‑directory.  
The agent will create the `analysis/` folder if it does not already exist.

| Step | Tool | Purpose | Output files (standard names) | Notes |
|------|------|---------|------------------------------|-------|
| 1 | `calculate_rmsd` | Compute backbone RMSD over time (protein backbone atoms). | `rmsd.dat`, `rmsd.png` | RMSD is aligned to the first frame; the plot shows the time series. |
| 2 | `calculate_rmsf` | Compute per‑residue RMSF for the whole protein. | `rmsf.dat`, `rmsf.png` | The agent will later extract residues 150–200 from `rmsf.dat` and produce a separate bar plot (`rmsf_150-200.png`). |
| 3 | `calculate_radius_of_gyration` | Compute radius of gyration over time. | `gyration.dat`, `gyration.png` | |
| 4 | `calculate_ligand_pocket_distance` | For holo trajectories, track the COM distance between ATP and the catalytic pocket (protein atoms within 5 Å of ATP in frame 0). | `ligand_pocket_distance.csv`, `ligand_pocket_distance.png` | The agent will first test whether the topology contains a ligand named “ATP”; if not, this step is skipped. |
| 5 | `calculate_dccm` | Compute the full‑protein Cα dynamic cross‑correlation matrix. | `dccm.dat`, `dccm_heatmap.png` | The matrix is aligned on Cα atoms; the heatmap visualises correlated motions. |
| 6 | `analyze_secondary_structure` | Run DSSP on every frame to obtain secondary‑structure assignments over time. | `dssp.dat`, `dssp.png` | The agent will also extract the subset of residues 150–200 from `dssp.dat` and generate a time‑evolution plot (`dssp_150-200.png`). |

After each tool finishes, the Analysis Agent will:

1. **Validate** that the output files exist and are non‑empty.  
2. **Generate subset plots** (residues 150–200) using matplotlib:  
   * For RMSF: read `rmsf.dat`, slice the rows for residues 150–200, and create a bar plot `rmsf_150-200.png`.  
   * For DSSP: read `dssp.dat`, extract the secondary‑structure columns for residues 150–200, and plot the time evolution `dssp_150-200.png`.  
3. **Record metadata** (simulation name, date, number of frames, presence of ATP) in a small JSON file `analysis/metadata.json` so that downstream reporting knows whether the pocket‑distance metric was computed.

---

### 2.  Expected Outcomes

| Metric | File | Description |
|--------|------|-------------|
| Backbone RMSD | `analysis/rmsd.dat` / `analysis/rmsd.png` | Time‑series of backbone RMSD (Å). |
| Per‑residue RMSF | `analysis/rmsf.dat` / `analysis/rmsf.png` | RMSF profile (Å) for all residues. |
| RMSF 150–200 | `analysis/rmsf_150-200.png` | Bar plot of RMSF for residues 150–200. |
| Radius of gyration | `analysis/gyration.dat` / `analysis/gyration.png` | Time‑series of Rg (Å). |
| Ligand‑pocket COM distance | `analysis/ligand_pocket_distance.csv` / `analysis/ligand_pocket_distance.png` | COM distance (Å) between ATP and catalytic pocket over time (only if ATP present). |
| Cα DCCM | `analysis/dccm.dat` / `analysis/dccm_heatmap.png` | Full‑protein dynamic cross‑correlation matrix. |
| DSSP full protein | `analysis/dssp.dat` / `analysis/dssp.png` | Time‑evolution of secondary structure for all residues. |
| DSSP 150–200 | `analysis/dssp_150-200.png` | Secondary‑structure evolution for residues 150–200. |
| Metadata | `analysis/metadata.json` | Simulation details and flags. |

These files will be ready for the next phase, where the **Reporter Agent** will aggregate the apo‑vs‑holo differences across all four proteins and produce the comparative report requested by the user.

---

### 3.  Rationale for Tool Choices

* **`calculate_rmsd`** directly implements backbone RMSD calculation and outputs the required `.dat` and `.png`.  
* **`calculate_rmsf`** provides per‑residue RMSF; the agent handles the subset extraction and plotting.  
* **`calculate_radius_of_gyration`** gives the radius of gyration time series.  
* **`calculate_ligand_pocket_distance`** is the exact tool for the pocket‑COM metric defined in the user goal.  
* **`calculate_dccm`** produces the full‑protein DCCM; the difference between apo and holo will be computed later by the Reporter.  
* **`analyze_secondary_structure`** implements DSSP and supplies both the full‑protein and per‑residue time‑series needed.  
* The Analysis Agent’s internal plotting (matplotlib) is sufficient for the subset bar plots; no external plotting tool is required.

All required metrics are covered by the existing tool registry, so no custom tool creation is necessary. The plan strictly follows the user’s requested analyses and adheres to the prescribed file naming conventions.