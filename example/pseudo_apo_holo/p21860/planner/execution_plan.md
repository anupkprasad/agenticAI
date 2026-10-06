# Planner Execution Plan

**Generated:** 2026-10-06 11:36:29
**Phase:** single

## Overview

**Title:** Detailed Natural Language Execution Plan
**Agent sequence:** analysis_agent
**Subtask:** analysis_only

## Full Plan

**Goal**  
Perform a complete, per‑simulation analysis of the MD trajectory in  
`/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860/hpc/`.  
The analysis must generate all metrics requested in the user goal, store the
results in the simulation’s `analysis/` directory, and prepare the data for
later overlay and reporting steps.

**Analysis Agent Workflow**

1. **File discovery**  
   The Analysis Agent will locate the topology (`md.gro`), trajectory
   (`md.xtc`), and energy (`md.edr`) files in the `hpc/` sub‑directory.  
   It will create the output directory  
   `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860/analysis/` if it does not already exist.

2. **Backbone RMSD**  
   *Tool:* `calculate_rmsd`  
   *Command:* `calculate_rmsd(topology_file=md.gro, trajectory_file=md.xtc, reference_selection="protein and backbone")`  
   *Outputs:* `rmsd.dat` and `rmsd.png` in the analysis folder.  
   The RMSD is computed after aligning each frame to the first frame on the
   protein backbone.

3. **Per‑residue RMSF**  
   *Tool:* `calculate_rmsf`  
   *Command:* `calculate_rmsf(topology_file=md.gro, trajectory_file=md.xtc)`  
   *Outputs:* `rmsf.dat` and `rmsf.png`.  
   The RMSF file contains a column for each residue.  
   After the tool finishes, the Analysis Agent will parse `rmsf.dat`,
   extract the rows for residues 150–200 (if they exist), and write
   `rmsf_150-200.dat`.  A bar‑plot of these values will be produced as
   `rmsf_150-200.png` using the same plotting routine that generated
   `rmsf.png`.

4. **Radius of gyration**  
   *Tool:* `calculate_radius_of_gyration`  
   *Command:* `calculate_radius_of_gyration(topology_file=md.gro, trajectory_file=md.xtc)`  
   *Outputs:* `gyration.dat` and `gyration.png`.

5. **Ligand‑pocket COM distance (holo only)**  
   The agent first checks whether the trajectory contains an ATP ligand
   (`resname ATP`).  
   If ATP is present, it runs:  
   *Tool:* `calculate_ligand_pocket_distance`  
   *Command:* `calculate_ligand_pocket_distance(topology_file=md.gro, trajectory_file=md.xtc, ligand_selection="resname ATP", cutoff=5.0)`  
   *Outputs:* `ligand_pocket_distance.csv` and `ligand_pocket_distance.png`.  
   If ATP is absent (apo simulation), this step is skipped.

6. **Dynamic Cross‑Correlation Matrix (DCCM)**  
   *Tool:* `calculate_dccm`  
   *Command:* `calculate_dccm(topology_file=md.gro, trajectory_file=md.xtc, selection="protein and name CA")`  
   *Outputs:* `dccm.dat` and `dccm_heatmap.png`.  
   The DCCM is computed on the Cα atoms after aligning the trajectory to
   the first frame.

7. **Secondary structure (DSSP)**  
   *Tool:* `analyze_secondary_structure`  
   *Command:* `analyze_secondary_structure(topology_file=md.gro, trajectory_file=md.xtc)`  
   *Outputs:* `dssp.dat` and `dssp.png`.  
   The `.dat` file contains a column per residue per frame.  
   The agent will extract the rows for residues 150–200 and write
   `dssp_150-200.dat`.  A heat‑map of these residues over time will be
   saved as `dssp_150-200.png`.

8. **Post‑processing and file naming**  
   All output files use the standard basenames defined in the
   “STANDARD PER‑SIMULATION OUTPUT FILENAMES” table.  
   Qualified files (e.g., `rmsf_150-200.dat`) keep the same stem but
   include the qualifier to avoid overwriting the overall files.

9. **Reporting**  
   After the Analysis Agent finishes, the Reporter Agent will be invoked.
   It will read the analysis outputs, compare the metrics to literature
   values for the same protein, and generate a narrative report that
   discusses activation‑loop dynamics, allosteric regulation, and
   relevant MD/experimental studies.  The report will reference the
   computed metrics (RMSD, RMSF, Rg, DCCM, DSSP, COM distance) and
   highlight any deviations or confirmations of known behavior.

**Expected Outcomes**

- `analysis/rmsd.dat`, `analysis/rmsd.png` – backbone RMSD time series.  
- `analysis/rmsf.dat`, `analysis/rmsf.png`, `analysis/rmsf_150-200.dat`, `analysis/rmsf_150-200.png` – per‑residue RMSF and subset plot.  
- `analysis/gyration.dat`, `analysis/gyration.png` – radius of gyration.  
- `analysis/ligand_pocket_distance.csv`, `analysis/ligand_pocket_distance.png` – only for holo runs.  
- `analysis/dccm.dat`, `analysis/dccm_heatmap.png` – DCCM.  
- `analysis/dssp.dat`, `analysis/dssp.png`, `analysis/dssp_150-200.dat`, `analysis/dssp_150-200.png` – DSSP time series and subset.  
- A literature‑based report produced by the Reporter Agent that contextualizes these metrics.

This plan strictly follows the user goal, uses only the available analysis tools, and prepares the data for subsequent overlay and reporting steps.