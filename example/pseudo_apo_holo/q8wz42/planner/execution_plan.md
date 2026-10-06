# Planner Execution Plan

**Generated:** 2026-10-06 11:43:13
**Phase:** single

## Overview

**Title:** Detailed Natural Language Execution Plan
**Agent sequence:** analysis_agent
**Subtask:** analysis_only

## Full Plan

**Goal**  
Produce a complete set of trajectory‑derived metrics for the apo TITIN simulation (q8wz42) that will feed the final report.  
The required analyses are: backbone RMSD, per‑residue RMSF (overall and residues 150–200), radius of gyration, Cα dynamic cross‑correlation matrix (DCCM) with an optional overlay against a holo trajectory, and DSSP secondary‑structure evolution (overall and residues 150–200).  All results must be written to the working directory’s *analysis* folder using the standard basenames so that a later multi‑simulation step can collect and overlay them.

**Analysis Agent**  
The Analysis Agent will discover the topology (`md.gro`) and trajectory (`md.xtc`) automatically in the *hpc* sub‑folder, then invoke the built‑in analysis tools in the order below.  Each tool writes its own data file and a PNG plot; the Agent will also assemble a small set of summary tables that capture key statistics for each metric.

---

### 1. Backbone RMSD vs. time  
*Tool:* `calculate_rmsd`  
*Command:*  
- `topology_file = md.gro`  
- `trajectory_file = md.xtc`  
- `selection = "backbone"` (or `"protein"`, whichever the tool defaults to for backbone atoms)  
- `output_file = rmsd.dat` (time‑series of RMSD values)  
- The tool will automatically generate `rmsd.png` in the *analysis* folder.  

*Outcome:* A time‑series plot of backbone RMSD and a CSV of the values for downstream statistics.

---

### 2. Per‑residue RMSF (overall)  
*Tool:* `calculate_rmsf`  
*Command:*  
- `topology_file = md.gro`  
- `trajectory_file = md.xtc`  
- `selection = "protein"` (all Cα atoms)  
- `output_file = rmsf.dat`  
- The tool will also produce `rmsf.png`.  

*Outcome:* RMSF profile for every residue and a bar plot.

---

### 3. Per‑residue RMSF (residues 150–200)  
*Tool:* `calculate_rmsf` (again, with a restricted selection)  
*Command:*  
- `selection = "resid 150-200"`  
- `output_file = rmsf_150to200.dat`  
- Plot will be `rmsf_150to200.png`.  

*Outcome:* A focused RMSF bar plot for the activation‑loop region.

---

### 4. Radius of gyration  
*Tool:* `calculate_radius_of_gyration`  
*Command:*  
- `topology_file = md.gro`  
- `trajectory_file = md.xtc`  
- `output_file = gyration.dat`  
- Plot will be `gyration.png`.  

*Outcome:* Time‑series of the protein’s radius of gyration.

---

### 5. Dynamic Cross‑Correlation Matrix (DCCM)  
*Tool:* `calculate_dccm`  
*Command:*  
- `topology_file = md.gro`  
- `trajectory_file = md.xtc`  
- `selection = "protein"` (Cα atoms)  
- `output_file = dccm.dat`  
- Plot will be `dccm_heatmap.png`.  

*Optional holo overlay:*  
The Agent will check for a holo trajectory in the sibling directory (`/home/.../holo/q8wz42/hpc/md.xtc`).  
If found, it will run the same `calculate_dccm` on the holo file, producing `dccm_holo.dat` and `dccm_holo_heatmap.png`.  
Then it will invoke `plot_dccm_difference` with `reference_dccm_file = dccm.dat` and `compare_dccm_file = dccm_holo.dat` to generate `dccm_difference_heatmap.png`.  
If no holo trajectory is present, only the apo DCCM will be produced.

*Outcome:* Full‑protein DCCM heatmap(s) and, if available, a difference map highlighting ligand‑induced changes.

---

### 6. DSSP secondary‑structure evolution  
*Tool:* `analyze_secondary_structure`  
*Command (overall):*  
- `topology_file = md.gro`  
- `trajectory_file = md.xtc`  
- `output_file = dssp.dat`  
- Plot will be `dssp.png`.  

*Command (residues 150–200):*  
- The same tool can be run with a selection `"resid 150-200"` (if supported) or the Agent can post‑process `dssp.dat` to extract the region.  
- Output will be `dssp_150to200.dat` and `dssp_150to200.png`.  

*Outcome:* Heatmaps of secondary‑structure assignment over time for the whole protein and for the activation‑loop region.

---

### 7. Summary tables  
The Analysis Agent will read each of the data files it produced and compute a concise set of statistics:

| Metric | Statistics | Output file |
|--------|------------|-------------|
| RMSD | mean, std, min, max | `summary_rmsd.csv` |
| RMSF (overall) | mean, std, max residue | `summary_rmsf_overall.csv` |
| RMSF (150–200) | mean, std, max residue | `summary_rmsf_150to200.csv` |
| Radius of gyration | mean, std, min, max | `summary_gyration.csv` |
| DCCM | mean absolute correlation, number of positively/negatively correlated pairs | `summary_dccm.csv` |
| DSSP | fraction of time in helix, sheet, turn, coil (overall and 150–200) | `summary_dssp.csv` |

Each table will be a plain CSV with a header row, ready for inclusion in the final report.

---

### 8. File layout (in `/home/.../analysis/`)  

```
rmsd.dat          rmsd.png
rmsf.dat           rmsf.png
rmsf_150to200.dat  rmsf_150to200.png
gyration.dat       gyration.png
dccm.dat           dccm_heatmap.png
dccm_holo.dat      dccm_holo_heatmap.png   (if holo exists)
dccm_difference_heatmap.png   (if holo exists)
dssp.dat           dssp.png
dssp_150to200.dat  dssp_150to200.png
summary_rmsd.csv
summary_rmsf_overall.csv
summary_rmsf_150to200.csv
summary_gyration.csv
summary_dccm.csv
summary_dssp.csv
```

All files will be written directly to the *analysis* directory; no intermediate directories will be created.

---

### 9. Execution Sequence (high‑level)

1. **Discover files** – Agent locates `md.gro` and `md.xtc` in the *hpc* folder.  
2. **Run backbone RMSD** – `calculate_rmsd`.  
3. **Run overall RMSF** – `calculate_rmsf`.  
4. **Run RMSF 150–200** – `calculate_rmsf` with restricted selection.  
5. **Run radius of gyration** – `calculate_radius_of_gyration`.  
6. **Run DCCM (apo)** – `calculate_dccm`.  
7. **Check for holo trajectory** – if present, run DCCM on holo and then `plot_dccm_difference`.  
8. **Run DSSP (overall)** – `analyze_secondary_structure`.  
9. **Run DSSP (150–200)** – either a second run with selection or post‑processing.  
10. **Generate summary tables** – read all data files, compute statistics, write CSVs.  
11. **Log completion** – write a short log file summarizing the number of frames processed and any warnings.

---

**Expected Outcomes**  
At the end of this workflow the *analysis* folder will contain all requested plots and CSV tables.  These files provide the quantitative backbone for the final report, allowing the Reporter Agent to correlate simulation observables with the literature on TITIN activation‑loop conformations and allosteric regulation.