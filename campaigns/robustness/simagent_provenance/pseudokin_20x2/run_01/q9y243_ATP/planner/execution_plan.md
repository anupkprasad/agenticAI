# Planner Execution Plan

**Generated:** 2026-09-23 13:40:22
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis → Reporter):**  
1. Using the existing 200‑ns trajectories for the q9y243 (AKT3) holo complex (protein + ATP, no crystallographic Mg/ions), compute the ten scalar dynamics descriptors per replicate (ATP COM distance & angle to the consensus pocket, pocket χ₁ circular mean & SD, Cα RMSF mean & SD, N‑↔C lobe DCCM mean, shared‑reference PCA scalar).  
2. Average each descriptor across the two replicates, generate full‑trajectory plots, and assemble the resulting 10‑column feature table.  
3. Perform Ward hierarchical clustering on the feature table, produce a dendrogram (with a k = 4 cut highlighted) and a robust z‑score/IQR‑scaled heatmap of the descriptors.  
4. Compile all plots, descriptor values, clustering results, and a brief literature context into a single HTML report for the case_id “protein_with_ligand.”  

All steps should be performed only on the specified system; no additional preprocessing, simulation setup, or new trajectories are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q9y243_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
