# Planner Execution Plan

**Generated:** 2026-09-23 19:05:13
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis and Reporter Agents**

1. **Analysis Agent**: Process the existing 200‑ns trajectories for all 37 protein‑ATP holo structures (protein + ligand, ions and water included). Compute the ten required scalar descriptors (ATP COM distance mean/SD, ATP–pocket axis angle mean/SD, pocket side‑chain χ₁ circular mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral‑PCA landscape entropy) by averaging over the two replicates. Save each system’s descriptor vector and intermediate plots (e.g., DCCM heatmaps, χ₁ histograms) in `/home/akp66103/.../p23458_ATP/analysis/` using standard basenames without a label prefix.

2. **Reporter Agent**: Assemble the 37 × 10 descriptor table, perform Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a single dendrogram plus feature‑heatmap panel. Produce a concise HTML report under `/home/akp66103/.../p23458_ATP/reporter/` that includes the clustering output, a literature‑context summary, and a note that a k = 4 cut is suggested for interpretation while displaying the full tree. No new simulations, preprocessing, or solvation steps should be invoked.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p23458_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
