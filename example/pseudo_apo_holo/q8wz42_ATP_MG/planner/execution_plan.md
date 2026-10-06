# Planner Execution Plan

**Generated:** 2026-10-06 11:43:29
**Phase:** single

## Overview

**Title:** Detailed Natural Language Execution Plan
**Agent sequence:** analysis_agent
**Subtask:** analysis_only

## Full Plan

**Goal**  
Produce a complete per‑simulation trajectory analysis for the eight 1‑ns MD runs (four apo, four holo) of ERBB3, VRK3, MLKL, and TITIN.  
For each system the following metrics must be calculated and saved in the standard filenames under the shared *analysis* directory:

| Metric | Output files (standard names) |
|--------|------------------------------|
| Backbone RMSD | `rmsd.dat`, `rmsd.png` |
| Per‑residue RMSF (full) | `rmsf.dat`, `rmsf.png` |
| Per‑residue RMSF (150–200) | `rmsf_150-200.dat`, `rmsf_150-200.png` |
| Radius of gyration | `gyration.dat`, `gyration.png` |
| COM distance (ATP–pocket, holo only) | `ligand_pocket_distance.csv`, `ligand_pocket_distance.png` |
| Cα DCCM | `dccm.dat`, `dccm_heatmap.png` |
| DSSP (full) | `dssp.dat`, `dssp.png` |
| DSSP (150–200) | `dssp_150-200.dat`, `dssp_150-200.png` |

The Analysis Agent will discover the topology (`*.gro`), trajectory (`*.xtc`), and energy (`*.edr`) files automatically in each *hpc* sub‑directory.  No preprocessing or trajectory wrapping is required.

---

### Analysis Agent Workflow

1. **File Discovery**  
   The agent scans `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8wz42_ATP_MG/hpc/` for pairs of topology/trajectory files.  For each pair it creates a context containing the paths to the `.gro`, `.xtc`, and `.edr` files.

2. **Backbone RMSD**  
   *Tool:* `calculate_rmsd`  
   *Selection:* `"backbone"` (or equivalent MDAnalysis selection)  
   *Output:* `rmsd.dat`, `rmsd.png` in the shared *analysis* directory.  
   The agent passes the topology and trajectory paths, requests a per‑frame RMSD against the first frame, and stores the time‑series and a line plot.

3. **Per‑Residue RMSF (full)**  
   *Tool:* `calculate_rmsf`  
   *Selection:* `"backbone"` (or all heavy atoms)  
   *Output:* `rmsf.dat`, `rmsf.png`.  
   The agent aligns the trajectory to the first frame before computing RMSF, then writes a CSV of residue‑index vs RMSF and a bar plot.

4. **Per‑Residue RMSF (150–200)**  
   *Tool:* `calculate_rmsf`  
   *Selection:* `"resid 150-200"` (only if residues 150–200 exist in the protein)  
   *Output:* `rmsf_150-200.dat`, `rmsf_150-200.png`.  
   The agent checks the residue range; if absent the step is skipped for that system.

5. **Radius of Gyration**  
   *Tool:* `calculate_radius_of_gyration`  
   *Output:* `gyration.dat`, `gyration.png`.  
   The agent computes the time‑series of the protein’s radius of gyration and plots it.

6. **COM Distance (ATP–pocket, holo only)**  
   *Tool:* `calculate_ligand_pocket_distance`  
   *Selection:* `ligand_selection="resname ATP"`, `cutoff=5.0`  
   *Output:* `ligand_pocket_distance.csv`, `ligand_pocket_distance.png`.  
   The agent first verifies that an ATP residue is present; if not, the step is skipped.  The tool identifies all protein atoms within 5 Å of ATP in frame 0, then tracks the COM distance over time.

7. **Cα Dynamic Cross‑Correlation Matrix**  
   *Tool:* `calculate_dccm`  
   *Selection:* `"protein and name CA"`  
   *Output:* `dccm.dat`, `dccm_heatmap.png`.  
   The agent aligns the trajectory on the protein backbone, computes the full DCCM, writes the matrix to a CSV, and produces a heat‑map.

8. **Secondary‑Structure Evolution (DSSP)**  
   *Tool:* `analyze_secondary_structure`  
   *Selection:* `"protein"`  
   *Output:* `dssp.dat`, `dssp.png`.  
   The agent records the DSSP assignment for every residue at every frame and plots a heat‑map of residue vs time.

9. **Secondary‑Structure Evolution (150–200)**  
   *Tool:* `analyze_secondary_structure`  
   *Selection:* `"resid 150-200"`  
   *Output:* `dssp_150-200.dat`, `dssp_150-200.png`.  
   If the residue range is absent, the step is omitted.

10. **Post‑processing for Apo‑vs‑Holo Comparison**  
    After all eight simulations have produced their per‑simulation outputs, the Analysis Agent signals completion.  The subsequent Reporter Agent will:

    - Load the standard files from all systems.
    - Overlay the RMSD, RMSF, radius of gyration, and COM distance plots for apo vs holo.
    - Compute statistical tables (mean, standard deviation, t‑tests) comparing apo and holo for each protein.
    - Use `plot_dccm_difference` to generate ΔC maps between apo and holo DCCMs for each protein.
    - Collate the DSSP evolution plots and highlight changes in residues 150–200.
    - Retrieve literature on activation‑loop conformations, allosteric regulation, and experimental dynamics for ERBB3, VRK3, MLKL, and TITIN, and annotate the plots and tables with relevant references.

---

### Expected Outcomes

- **Per‑simulation data files** (`*.dat`, `*.csv`) and **plots** (`*.png`) in `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8wz42_ATP_MG/analysis/`.
- **Overlay plots** and **statistical tables** comparing apo vs holo for each protein, generated by the Reporter Agent.
- A **final report** that integrates the simulation results with literature on activation‑loop dynamics and allosteric regulation for the four proteins.

All requested analyses are covered by the available tools (`calculate_rmsd`, `calculate_rmsf`, `calculate_radius_of_gyration`, `calculate_ligand_pocket_distance`, `calculate_dccm`, `plot_dccm_difference`, `analyze_secondary_structure`). No additional tool creation is required.