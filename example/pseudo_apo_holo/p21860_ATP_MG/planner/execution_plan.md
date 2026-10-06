# Planner Execution Plan

**Generated:** 2026-10-06 11:36:39
**Phase:** single

## Overview

**Title:** Detailed Natural Language Execution Plan
**Agent sequence:** analysis_agent
**Subtask:** analysis_only

## Full Plan

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

All output files will be placed under  
`/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/analysis/`.  
The filenames follow the convention:

- `rmsd.dat`, `rmsd.png`
- `rmsf.dat`, `rmsf.png`
- `gyration.dat`, `gyration.png`
- `dccm.dat`, `dccm_heatmap.png`
- `dssp.dat`, `dssp.png`
- `ligand_pocket_distance.csv`, `ligand_pocket_distance.png` (if holo)
- `rmsf_150-200.dat`, `rmsf_150-200.png`
- `dssp_150-200.dat`, `dssp_150-200.png`

No other files are written at this stage.

---

### 4. Summary of the Workflow

1. **Initialization** – The Analysis Agent locates the trajectory and topology files in the `hpc/` subdirectory and creates the `analysis/` folder if it does not exist.  
2. **Metric Computation** – Sequentially invoke the six tools listed above, each writing its own data and plot files.  
3. **Residue‑range Extraction** – Using the raw data files, filter residues 150–200 and generate the two bar/line plots.  
4. **Finalization** – All files are now present in the analysis directory, ready for the next phase of the overall workflow (cross‑simulation overlay, statistical tables, and reporter synthesis).

---

### 5. Notes for the Next Workflow Phase

- The difference maps (apo – holo) will be generated later by a combined analysis step that reads the `dccm.dat` files from both the apo and holo runs.  
- The statistical tables summarizing RMSD, RMSF, Rg, COM distance, and DCCM metrics across all eight simulations will also be assembled in that phase.  
- The Reporter Agent will later retrieve literature and correlate the per‑simulation results with known ATP‑binding and activation‑loop behavior.

---

**Conclusion**  
The plan above uses only the built‑in analysis tools, respects the per‑simulation scope, and produces exactly the files required for downstream combined analysis. No custom tool creation is necessary.