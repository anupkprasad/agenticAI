# Planner Execution Plan

**Generated:** 2026-09-23 13:25:06
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis & Reporting Agents**

1. **Analysis**: Using the already‑generated trajectories in *rep01* and *rep02*, compute the ten requested scalar dynamics descriptors (ATP COM distance, ATP orientation, pocket χ₁ mean/SD, Cα RMSF mean/SD, N‑↔C DCCM mean, shared‑reference PCA scalar) for every time point over the full 200 ns window. Average each descriptor across the two replicates, and create plots that display the full 200 ns trajectory of each descriptor.

2. **Feature Table & Clustering**: Assemble the averaged ten descriptors into a feature table for this system, apply Ward hierarchical clustering (with full tree and k = 4 cut optional), and generate a dendrogram plus a robustly scaled (z‑score/IQR) heatmap of the descriptor values.

3. **Reporting**: Compile the descriptor plots, clustering results, and a brief literature context into a single HTML report. The report must clearly state that the holo structure (protein + ATP ligand, ions excluded) was analyzed under the specified simulation conditions (amber99sb‑ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl).

**Constraints / Special Requirements**

- Only the holo system (protein + ATP ligand, no ions) is to be analyzed; no additional preprocessing or simulation steps are performed.  
- Trajectories are taken directly from the provided directories; no further equilibration or production runs are requested.  
- All outputs (plots, clustering, report) must be generated solely from the existing data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p23458_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
