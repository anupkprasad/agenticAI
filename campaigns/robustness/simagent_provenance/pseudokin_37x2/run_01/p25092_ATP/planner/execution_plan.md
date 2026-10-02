# Planner Execution Plan

**Generated:** 2026-09-23 19:14:01
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
For each of the 37 protein–ATP holo trajectories (already generated) perform the full analysis set: ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, protein DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
From the two 200 ns replicates compute the ten required scalar descriptors (ATP‑COM distance mean & SD, ATP orientation mean & SD, pocket χ₁ circular mean & SD, consensus‑mapped Cα RMSF mean & SD, N‑/C‑lobe DCCM mean, and shared‑reference dihedral‑PCA dynamics scalar), then average across replicates.  
Export the descriptor table, run Ward hierarchical clustering, and generate a dendrogram plus robust z‑score/IQR‑scaled heatmap, all saved under `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p25092_ATP/analysis/`.  
Create a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p25092_ATP/reporter/` that includes the clustering figure, heatmap, feature table, and brief literature context, marking a k=4 cut for interpretation but presenting the full dendrogram.  
All analyses respect the case_id `protein_with_ligand` (ligand included, ions and crystal waters excluded) and use the default GROMACS conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p25092_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
