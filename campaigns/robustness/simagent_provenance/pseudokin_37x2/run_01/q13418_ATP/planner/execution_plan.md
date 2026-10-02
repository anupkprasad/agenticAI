# Planner Execution Plan

**Generated:** 2026-09-23 19:45:59
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis + reporter only)**  

1. Using the existing 200 ns trajectories for each of the 37 protein–ATP holo structures, perform the requested analyses: ligand‑pocket distance, consensus‑DCCM, consensus‑RMSF, consensus‑torsions, DCCM, dihedral‑PCA, nearby, and protein RMSF.  
2. From the two replicates per system, compute the ten required scalar descriptors (ATP COM‑pocket distance mean/std, ATP orientation mean/std, pocket χ₁ circular mean/std, consensus‑mapped Cα RMSF mean/std, N‑lobe↔C‑lobe DCCM mean, and shared‑reference dihedral‑PCA entropy), and assemble them into a single feature table.  
3. Perform Ward hierarchical clustering on this table, generate a dendrogram and a robust z‑scaled heat‑map, and package all results in a concise HTML report.  
4. Write all raw analysis files (distance, rmsf, dccm, torsion, etc.) to `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13418_ATP/analysis/` using standard basenames (no label prefix).  
5. Place the final HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13418_ATP/reporter/`.  
6. Do not initiate any preprocessing, solvation, equilibration, production runs, or HPC submissions; all work is limited to analysis of the existing trajectories and report generation.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13418_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
