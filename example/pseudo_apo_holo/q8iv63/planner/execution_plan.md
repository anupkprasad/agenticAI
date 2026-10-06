# Planner Execution Plan

**Generated:** 2026-10-06 11:36:10
**Phase:** single

## Overview

**Title:** Detailed Natural Language Execution Plan
**Agent sequence:** analysis_agent
**Subtask:** analysis_only

## Full Plan

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
   - `trajectory_file` = `hpc/md.xtc`  
   - `selection` = `"protein and name CA"`  
   - `output_file` = `analysis/dccm.dat`  
   - `plot_file` = `analysis/dccm_heatmap.png`  

7. **DSSP – whole protein**  
   *Tool:* `analyze_secondary_structure`  
   *Parameters:*  
   - `topology_file` = `hpc/md.gro`  
   - `trajectory_file` = `hpc/md.xtc`  
   - `selection` = `"protein"`  
   - `output_file` = `analysis/dssp.dat`  
   - `plot_file` = `analysis/dssp.png`  

8. **DSSP – residues 150–200**  
   *Tool:* `analyze_secondary_structure`  
   *Parameters:*  
   - `topology_file` = `hpc/md.gro`  
   - `trajectory_file` = `hpc/md.xtc`  
   - `selection` = `"resid 150-200"`  
   - `output_file` = `analysis/dssp_150to200.dat`  
   - `plot_file` = `analysis/dssp_150to200.png`  

   *Conditional logic:*  
   As with RMSF, the agent verifies that residues 150–200 are present before running this step.

---

### Expected Outcomes

After the Analysis Agent completes the above steps, the `analysis/` directory will contain:

- `rmsd.dat` / `rmsd.png` – backbone RMSD vs. time  
- `rmsf.dat` / `rmsf.png` – per‑residue RMSF for the entire protein  
- `rmsf_150to200.dat` / `rmsf_150to200.png` – RMSF bar plot for residues 150–200 (if applicable)  
- `gyration.dat` / `gyration.png` – radius of gyration vs. time  
- `dccm.dat` / `dccm_heatmap.png` – Cα dynamic cross‑correlation matrix heatmap  
- `dssp.dat` / `dssp.png` – DSSP secondary‑structure evolution for the whole protein  
- `dssp_150to200.dat` / `dssp_150to200.png` – DSSP evolution for residues 150–200 (if applicable)

These files provide all the per‑trajectory metrics required for the subsequent cross‑simulation overlay and literature‑reporting phases. No additional analyses, plots, or tables are generated at this stage.