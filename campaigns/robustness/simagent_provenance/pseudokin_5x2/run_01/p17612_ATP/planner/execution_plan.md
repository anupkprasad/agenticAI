# Planner Execution Plan

**Generated:** 2026-09-23 10:54:28
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis → Reporter)**  

1. Using the already‑generated 200 ns production trajectories for the five holo complexes (p17612, o60674, p24941, q8ivt5, q13418), compute the ten required scalar descriptors for each system, including the mean/std of ATP COM‑pocket distance, mean/std of ATP axis angle, pocket χ₁ circular mean/std, consensus‑mapped Cα RMSF mean/std, N‑/C‑lobe DCCM mean correlation, and the shared‑reference dihedral PCA dynamics scalar.  
2. Assemble the ten descriptors from all five systems into a single feature table and apply Ward hierarchical clustering (z‑score/IQR scaling) to generate a dendrogram and a heatmap of the feature matrix.  
3. Generate a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p17612_ATP/reporter/` that includes the dendrogram, heatmap, a k = 4 cut for interpretation, and brief literature context.  
4. All analyses must respect the “protein_with_ligand” directive: include ATP and any necessary ions, but exclude crystallographic Mg/ions unless required.  
5. Output the scalar descriptor files, feature table, dendrogram, heatmap, and HTML report to the specified `analysis/` and `reporter/` directories, ensuring no new preprocessing, simulation setup, or trajectory generation is performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p17612_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
