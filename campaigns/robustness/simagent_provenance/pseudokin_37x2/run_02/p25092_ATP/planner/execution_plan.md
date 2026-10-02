# Planner Execution Plan

**Generated:** 2026-09-23 22:41:36
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased goal for the analysis and reporter agents**

1. For the trajectory files in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP/rep01` and `rep02`, compute the ten requested scalar descriptors per system (averaged over the two 200 ns replicas).  
2. Identify the ATP‑binding pocket as the residues within 15 Å of ATP in the reference KAPCA (p17612) structure, map those pocket residues onto the other 36 proteins via a global MAFFT MSA, and use the mapped residues to calculate pocket χ₁ statistics and consensus‑mapped Cα RMSF.  
3. Generate the following outputs in the working directory:  
   * `analysis/feature_table.csv` containing all ten descriptors for each protein (with columns for mean and standard deviation where appropriate).  
   * `analysis/dccm_plots/` containing N‑lobe ↔ C‑lobe DCCM heatmaps for each system.  
   * `analysis/pca_landscape_entropy.txt` listing the shared‑reference dihedral PCA entropy values.  
   * `analysis/dendrogram.svg` and `analysis/heatmap.svg` showing Ward hierarchical clustering (robust z‑score/IQR scaling) of the ten‑descriptor feature table.  
4. Produce an HTML report in `reporter/summary.html` that includes: a concise literature context, the full dendrogram and heatmap panels, a table of the ten descriptors for each protein, and a brief discussion of the clustering results (highlighting the k = 4 cut but preserving the full tree).  

All analysis is to be performed on the existing 200 ns trajectories; no preprocessing, simulation setup, or new simulations are to be executed. The ligand (ATP) must be included; crystallographic ions are excluded.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
