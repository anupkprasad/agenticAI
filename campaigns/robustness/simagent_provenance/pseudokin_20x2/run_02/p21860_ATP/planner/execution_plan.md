# Planner Execution Plan

**Generated:** 2026-09-23 15:49:18
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis and Reporting Agents**

1. Using the existing 200‑ns production trajectories from the two replicas (rep01 and rep02) of the p21860_ATP holo complex, compute the ten required scalar descriptors: (i) mean ± std of ATP COM distance to the consensus pocket, (ii) mean ± std of ATP orientation versus pocket axis, (iii) circular mean ± std of pocket side‑chain χ₁, (iv) mean ± std of consensus‑mapped Cα RMSF, (v) mean correlation of the N‑lobe ↔ C‑lobe DCCM, and (vi) shared‑reference dihedral PCA dynamics scalar relative to KAPCA.  
2. Assemble these descriptors for all 20 holo systems into a single feature table, apply robust z‑score/IQR scaling, and perform Ward hierarchical clustering.  
3. Generate a dendrogram and a feature‑heatmap panel (full tree, with a k = 4 cut optionally annotated).  
4. Produce a combined HTML report located in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p21860_ATP/reporter/` that summarizes the results, includes the cluster visualization, and provides brief literature context for each protein–ATP holo complex.  

All work is limited to analysis and reporter stages; no new preprocessing, simulation setup, or trajectory generation is required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p21860_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
