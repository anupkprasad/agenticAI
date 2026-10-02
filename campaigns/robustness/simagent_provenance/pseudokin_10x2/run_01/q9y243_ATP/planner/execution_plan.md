# Planner Execution Plan

**Generated:** 2026-09-22 17:31:16
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting Goal**

1. **Analysis** – For each of the ten protein–ATP holo PDBs (p17612, o60674, p24941, q8ivt5, q13418, p00533, p23458, q6vab6, q92519, q9y243), analyze the two already‑generated 200 ns production MD trajectories (protein + ATP only, no crystallographic ions or water). Compute the ten scalar dynamics descriptors listed (ATP COM distance mean/SD, ATP orientation mean/SD, pocket χ1 mean/SD, Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral PCA scalar). Average the descriptor values over the two replicates for each system.

2. **Reporting** – Assemble the ten‑descriptor vector for all ten systems into a single feature table. Perform Ward hierarchical clustering, plot a dendrogram and a robustly scaled (z‑score/IQR) heatmap, and highlight a k = 4 cut for interpretation. Generate individual plots of each descriptor time series (full 200 ns), and compile all results, plots, and brief literature context into a single HTML report. No preprocessing, simulation setup, or new MD runs are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q9y243_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
