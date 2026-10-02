# Planner Execution Plan

**Generated:** 2026-09-23 20:22:10
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the already‑generated 200 ns trajectories for all 37 protein–ATP holo structures in the working directory, computing ligand pocket distances, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF, and from these extract the ten required scalar dynamics descriptors (ATP COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ mean/SD, consensus‑Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral‑PCA entropy) for each system.  
Store all per‑trajectory analysis results in /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8nb16_ATP/analysis/ using standard basenames (no label prefix).  
After descriptor extraction, assemble a feature table for the 37 systems, perform Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a dendrogram plus a feature‑heatmap panel, saving the plots in the same analysis directory.  
Produce a concise HTML report that summarizes literature context, descriptor statistics, and clustering interpretation (including a k = 4 cut for discussion), embedding the dendrogram and heatmap, and place the report under /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8nb16_ATP/reporter/.  
No new preprocessing, simulation setup, or HPC submission is required; analysis is limited to the pre‑existing trajectories.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8nb16_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
