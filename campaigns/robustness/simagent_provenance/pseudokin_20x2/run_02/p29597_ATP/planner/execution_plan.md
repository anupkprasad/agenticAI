# Planner Execution Plan

**Generated:** 2026-09-23 16:14:08
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis and Reporting Goal**

1. Perform the requested analyses on the already‑generated 200 ns trajectories for all 20 human protein–ATP holo structures (p17612–q13308).  
2. For each trajectory, compute the ten scalar dynamics descriptors defined by the user (ATP COM distance mean & SD, ATP–pocket axis mean & SD, pocket χ₁ circular mean & SD, consensus‑mapped Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral‑PCA dynamics scalar) and the additional per‑system analyses (ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF).  
3. Assemble a single feature table with systems as rows and the ten descriptors as columns, apply robust z‑score/IQR scaling, and perform Ward hierarchical clustering to generate a dendrogram and a feature‑heatmap panel.  
4. Compile all results, plots, and literature context into one combined HTML report stored in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p29597_ATP/reporter/`.  
5. All analyses must respect the default simulation conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl) and the KAPCA (p17612) pocket definition, excluding any crystallographic Mg/ions from the source PDB.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p29597_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
