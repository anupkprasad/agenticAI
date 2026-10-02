# Planner Execution Plan

**Generated:** 2026-09-23 15:45:45
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the existing 200 ns trajectories for each of the 20 protein–ATP holo structures, using only the protein and ATP coordinates (exclude crystallographic ions and water). Compute the ten required scalar descriptors per trajectory (ATP COM distance & orientation mean & SD, pocket χ1 mean & SD, consensus‑mapped Cα RMSF mean & SD, N‑lobe/C‑lobe DCCM mean, and shared‑reference dihedral PCA distance to the KAPCA PC space) and average the two replicates. Assemble the descriptor values into a single feature table, scale them with robust z‑score/IQR, perform Ward hierarchical clustering, and generate a dendrogram plus a feature‑heatmap panel; place all analysis outputs under `/analysis/`. Produce a combined HTML report containing literature context, clustering results, and visual panels, and save it under `/reporter/`. Use KAPCA (p17612) as the reference to define the consensus ATP‑binding pocket (15 Å cutoff) and map it onto the other proteins via a global MAFFT MSA.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/o43187_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
