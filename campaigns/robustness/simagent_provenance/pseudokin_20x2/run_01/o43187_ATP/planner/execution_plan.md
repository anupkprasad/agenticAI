# Planner Execution Plan

**Generated:** 2026-09-23 13:44:27
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis → reporter only)**  

1. Perform analysis on the two 200‑ns production replicas (rep01 and rep02) of the o43187 ATP‑holo complex in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o43187_ATP`.  
2. For each replicate compute the ten scalar descriptors (ATP COM distance/angle, pocket χ₁ mean & SD, Cα RMSF mean & SD, N↔C DCCM mean, shared‑reference PCA scalar) and then average the results across the two replicas.  
3. Generate full‑trajectory plots for each replica (no truncation), and create an HTML report that displays the trajectory visualizations, the descriptor table, and a brief literature context.  
4. Repeat steps 1–3 for all 20 holo complexes; then combine the ten‑descriptor tables, run Ward hierarchical clustering, and append a dendrogram plus a robustly scaled heat‑map to the final report.  
5. All analyses should consider only the protein and ATP ligand (exclude crystallographic ions and any water molecules).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o43187_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
