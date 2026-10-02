# Planner Execution Plan

**Generated:** 2026-09-22 18:03:42
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the 200 ns trajectories already present for the ten protein–ATP holo complexes (case_id = protein_with_ligand) and, for each system, compute the following descriptors: ligand‑pocket COM distance (mean & std), pocket‑axis orientation angle (mean & std), pocket side‑chain χ₁ circular mean & std, consensus‑mapped Cα RMSF (mean & std), N‑lobe/C‑lobe DCCM mean correlation, shared‑reference φ/ψ/χ₁ dihedral‑PCA entropy, plus the requested per‑trajectory analyses (consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF).  
Aggregate the ten scalar descriptors into a single feature matrix, perform Ward hierarchical clustering, and generate a dendrogram and heatmap (robust z‑score/IQR scaling) with a k = 4 cut line; place all plots and numeric tables under  
`/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p17612_ATP/analysis/` and the dendrogram/heatmap in the reporter subdirectory.  
Produce a concise HTML report (including brief literature context) in  
`/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p17612_ATP/reporter/`.  
No new preprocessing, simulation, or HPC steps are to be executed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p17612_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
