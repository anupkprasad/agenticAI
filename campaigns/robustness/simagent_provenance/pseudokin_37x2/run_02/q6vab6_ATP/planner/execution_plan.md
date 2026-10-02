# Planner Execution Plan

**Generated:** 2026-09-23 23:20:26
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

1. **Analysis**: Using the already‑generated 200‑ns trajectories for the 37 protein–ATP holo complexes (each with two independent replicas), compute the ten required scalar descriptors (ATP COM distance mean & SD, ATP orientation mean & SD, pocket χ₁ circular mean & SD, consensus‑mapped Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral‑PCA distance) for every system, then average across the two replicas. Map the ATP‑binding pocket from the KAPCA (p17612) reference onto each target using a global MAFFT alignment and a 15 Å cutoff for pocket residues. Generate a unified feature table (37 × 10) stored under `/home/akp66103/workspace/.../analysis/`.

2. **Clustering & Visualisation**: Perform Ward hierarchical clustering on the z‑scored feature table, output the full dendrogram and a heatmap of the scaled descriptors (stored under `/home/.../analysis/`). Identify a k = 4 cut for interpretability but keep the complete tree.

3. **Reporter**: Compile a concise HTML report in `/home/.../reporter/` that includes the dendrogram, heatmap, a brief literature context for pseudokinase vs active kinase behavior, and a summary of the ten descriptor values per protein. No preprocessing, simulation setup, or new trajectory generation should be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
