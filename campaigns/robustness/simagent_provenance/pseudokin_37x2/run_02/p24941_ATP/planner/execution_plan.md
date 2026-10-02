# Planner Execution Plan

**Generated:** 2026-09-23 22:30:43
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

For each of the 37 human protein–ATP holo structures (including p24941_ATP), compute the ten required scalar descriptors (ATP COM distance mean & SD, ATP orientation mean & SD, pocket χ₁ mean & SD, consensus Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral‑PCA landscape entropy) by averaging the two 200 ns production replicas per system. Store all descriptor files and intermediate plots in  
`/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP/analysis/` using the standard basenames (no label prefix).  

Compile the descriptor matrix for all 37 systems, perform Ward hierarchical clustering with robust z‑score/IQR scaling, and output a single dendrogram and feature‑heatmap panel in the same analysis directory.  

Generate a concise HTML report summarizing the literature context, descriptor statistics, clustering results, and visualizations, and place it in  
`/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP/reporter/`.  

All analyses must use the existing trajectories (protein + ATP ligand, no crystallographic Mg/ions), and default simulation conditions (amber99sb-ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl) are assumed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
