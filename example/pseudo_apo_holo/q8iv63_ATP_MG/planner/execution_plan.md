# Planner Execution Plan

**Generated:** 2026-10-06 11:36:54
**Phase:** single

## Overview

**Title:** Detailed Natural Language Execution Plan
**Agent sequence:** analysis_agent
**Subtask:** analysis_only

## Full Plan

**Goal**  
Produce all requested trajectory‑level metrics for the single simulation  
`/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63_ATP_MG`.  
The analysis must generate the standard output files in  
`/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63_ATP_MG/analysis/` so that a later, multi‑simulation phase can overlay and tabulate the results.

**Analysis Agent**  
The Analysis Agent will discover the topology (`md.gro`), trajectory (`md.xtc`) and energy (`md.edr`) files in the `hpc/` subdirectory, create the `analysis/` directory if it does not yet exist, and then invoke the built‑in analysis tools in a logical sequence.  No external shell commands or custom tools are required.

**Execution Sequence**

1. **Backbone RMSD**  
   *Tool:* `calculate_rmsd`  
   *Arguments:*  
   - `topology_file` → `/home/.../q8iv63_ATP_MG/hpc/md.gro`  
   - `trajectory_file` → `/home/.../q8iv63_ATP_MG/hpc/md.xtc`  
   - `reference_selection` → `"protein and backbone"` (default)  
   *Outputs:* `analysis/rmsd.dat`, `analysis/rmsd.png`  

2. **Per‑Residue RMSF (full protein)**  
   *Tool:* `calculate_rmsf`  
   *Arguments:* same topology/trajectory, alignment on protein Cα.  
   *Outputs:* `analysis/rmsf.dat`, `analysis/rmsf.png`  

3. **Per‑Residue RMSF (residues 150–200)**  
   *Tool:* `calculate_rmsf` with a selection file.  
   *Procedure:*  
   - Create a temporary JSON file listing residues 150–200 (`"mda_selection_ca"`).  
   - Run `calculate_rmsf` with `selection_from_file` pointing to that JSON.  
   *Outputs:* `analysis/rmsf_150to200.dat`, `analysis/rmsf_150to200.png`  

4. **Radius of Gyration**  
   *Tool:* `calculate_radius_of_gyration`  
   *Arguments:* same topology/trajectory, selection `"protein"`.  
   *Outputs:* `analysis/gyration.dat`, `analysis/gyration.png`  

5. **Ligand‑Pocket COM Distance (ATP vs catalytic pocket)**  
   *Tool:* `calculate_ligand_pocket_distance`  
   *Arguments:*  
   - `ligand_selection` → `"resname ATP"`  
   - `cutoff` → `5.0` Å (standard pocket definition)  
   - `output_file` → `analysis/ligand_pocket_distance.csv`  
   *Outputs:* `analysis/ligand_pocket_distance.csv`, `analysis/ligand_pocket_distance.png`  

6. **Dynamic Cross‑Correlation Matrix (DCCM)**  
   *Tool:* `calculate_dccm`  
   *Arguments:* same topology/trajectory, selection `"protein and backbone"`.  
   *Outputs:* `analysis/dccm.dat`, `analysis/dccm_heatmap.png`  

7. **Secondary Structure Evolution (whole protein)**  
   *Tool:* `analyze_secondary_structure`  
   *Arguments:* same topology/trajectory.  
   *Outputs:* `analysis/dssp.dat`, `analysis/dssp.png`  

8. **Secondary Structure Evolution (residues 150–200)**  
   *Procedure:*  
   - Run `analyze_secondary_structure` once (as above).  
   - Post‑process the resulting `dssp.dat` to extract rows for residues 150–200.  
   - Write the subset to `analysis/dssp_150to200.dat` and generate a bar plot `analysis/dssp_150to200.png`.  
   *Outputs:* `analysis/dssp_150to200.dat`, `analysis/dssp_150to200.png`  

**Expected Outcomes**

- A complete set of time‑series files (`*.dat`/`*.csv`) and corresponding PNG plots for each requested metric, all stored in the `analysis/` directory with the exact basenames required for downstream aggregation.  
- The RMSF and DSSP subset files will allow the later overlay phase to compare the 150–200 region across all eight systems.  
- No cross‑simulation calculations are performed here; the plan strictly follows the “individual simulation only” scope.  

**Why These Tools?**  
All requested metrics map directly to existing Analysis Agent tools:  
- RMSD → `calculate_rmsd`  
- RMSF → `calculate_rmsf` (with selection file for the 150–200 window)  
- Radius of gyration → `calculate_radius_of_gyration`  
- COM distance → `calculate_ligand_pocket_distance` (appropriate for ATP binding pocket)  
- DCCM → `calculate_dccm`  
- DSSP → `analyze_secondary_structure` (subset extraction handled post‑run)  

No custom tool creation is required, so the workflow remains fully automated within the provided framework.