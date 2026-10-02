# Planner Execution Plan

**Generated:** 2026-09-23 15:26:10
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis and Reporter**

1. Analyze the 20 existing protein–ATP holo trajectory datasets (two 200 ns replicates per system) located in the working directories, computing the ten specified scalar dynamics descriptors per system and per replicate, then average the results across replicates.  
2. Map the ATP‑binding pocket defined by the KAPCA (p17612) reference onto each protein via global sequence alignment, and include pocket‑related metrics (ATP COM distance, orientation, χ₁ circular mean/SD) in the descriptor set.  
3. Assemble the averaged descriptor matrix into a feature table, perform Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a dendrogram and a feature‑heatmap panel.  
4. Compile all analysis results and visualizations into a single HTML report with concise literature context, placing the report in the `reportr` subdirectory of each system’s working directory.  
5. Write all intermediate and final outputs for each system under `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/<system_id>/analysis/`, ensuring that no new preprocessing, simulation, or solvation steps are executed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p23458_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
