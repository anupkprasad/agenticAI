# Planner Execution Plan

**Generated:** 2026-10-06 11:42:44
**Phase:** single

## Overview

**Title:** Detailed Natural Language Execution Plan
**Agent sequence:** analysis_agent
**Subtask:** analysis_only

## Full Plan

**Goal**  
The objective is to extract a comprehensive set of dynamical and structural descriptors from the eight existing 1‑ns MD trajectories (four proteins, each in apo and holo form).  For every trajectory the Analysis Agent must generate the standard data and plot files that will later be combined by the Reporter Agent into overlay visualisations and statistical tables.  No new preprocessing, simulation set‑up, or HPC submission steps are required.

**Analysis**  
The Analysis Agent will perform the following calculations for each simulation directory:

| Metric | Tool | Output files (standard names) | Notes |
|--------|------|------------------------------|-------|
| Backbone RMSD | `calculate_rmsd` | `rmsd.dat`, `rmsd.png` | Uses the protein backbone as the reference; the tool automatically aligns the trajectory. |
| Per‑residue RMSF | `calculate_rmsf` | `rmsf.dat`, `rmsf.png` | After the full‑protein RMSF is produced, the agent will filter the data to residues 150–200 (if they exist) and write `rmsf_150-200.dat` and `rmsf_150-200.png`. |
| Radius of gyration | `calculate_radius_of_gyration` | `gyration.dat`, `gyration.png` | Whole‑protein Rg over time. |
| Ligand‑pocket COM distance (holo only) | `calculate_ligand_pocket_distance` | `ligand_pocket_distance.csv`, `ligand_pocket_distance.png` | Defines the catalytic pocket as all protein atoms within 5 Å of ATP at frame 0. |
| Dynamic Cross‑Correlation Matrix | `calculate_dccm` | `dccm.dat` (internal), `dccm_heatmap.png` | Full‑protein Cα DCCM. |
| DCCM difference (apo vs holo) | `plot_dccm_difference` | `dccm_difference.png` | Requires the two DCCM files from the apo and holo runs of the same protein. |
| DSSP secondary‑structure evolution | `analyze_secondary_structure` | `dssp.dat`, `dssp.png` | Whole‑protein DSSP time series. The agent will also extract residues 150–200 to produce `dssp_150-200.dat` and `dssp_150-200.png`. |

All output files are written to the simulation’s `analysis/` sub‑directory, preserving the exact basenames required for later aggregation.

**Execution Sequence**  
For each of the eight simulation directories the Analysis Agent will:

1. **Discover Files** – Locate the topology (`*.gro`), trajectory (`*.xtc`), and energy (`*.edr`) files automatically; the agent will use the directory structure provided.  
2. **Run Backbone RMSD** – Invoke `calculate_rmsd` with the topology and trajectory; capture `rmsd.dat` and `rmsd.png`.  
3. **Run Per‑Residue RMSF** – Invoke `calculate_rmsf`; after completion, read `rmsf.dat`, filter for residues 150–200, and write the subset files.  
4. **Run Radius of Gyration** – Invoke `calculate_radius_of_gyration`; collect `gyration.dat` and `gyration.png`.  
5. **Run Ligand‑Pocket Distance (holo only)** – If the simulation is a holo run, invoke `calculate_ligand_pocket_distance`; collect the CSV and PNG.  
6. **Run DCCM** – Invoke `calculate_dccm`; store the matrix and heat‑map.  
7. **Run DCCM Difference** – After both apo and holo DCCMs for a protein are available, invoke `plot_dccm_difference` with the two files; produce `dccm_difference.png`.  
8. **Run DSSP** – Invoke `analyze_secondary_structure`; after completion, filter `dssp.dat` for residues 150–200 and write the subset files.  

The agent will log each step, ensuring that any missing data (e.g., residues 150–200 not present in a protein) is noted and the corresponding subset files are omitted gracefully.

**Expected Outcomes**  
At the end of the Analysis Agent’s run, every simulation directory will contain:

- `rmsd.dat`, `rmsd.png`
- `rmsf.dat`, `rmsf.png`, `rmsf_150-200.dat`, `rmsf_150-200.png` (if applicable)
- `gyration.dat`, `gyration.png`
- `ligand_pocket_distance.csv`, `ligand_pocket_distance.png` (holo only)
- `dccm.dat`, `dccm_heatmap.png`
- `dccm_difference.png` (apo–holo pair)
- `dssp.dat`, `dssp.png`, `dssp_150-200.dat`, `dssp_150-200.png` (if applicable)

These files provide all the time‑series, per‑residue, and matrix data required for the Reporter Agent to generate overlay plots, statistical tables, and a literature‑linked discussion of activation‑loop dynamics and allosteric regulation for each protein.  No additional tools are needed beyond those listed, and the workflow respects the constraints of the analysis‑only phase.