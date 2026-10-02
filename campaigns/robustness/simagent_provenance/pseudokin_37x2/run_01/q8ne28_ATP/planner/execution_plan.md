# Planner Execution Plan

**Generated:** 2026-09-23 20:26:59
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
For each of the 37 protein–ATP holo trajectories (protein + ATP ligand, crystallographic ions removed) in the current working directory, compute the per‑trajectory analyses: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby, and protein RMSF.  
From the two 200‑ns replicates per system, extract the ten scalar descriptors (ATP COM distance mean/std, ATP orientation mean/std, pocket χ₁ mean/std, consensus Cα RMSF mean/std, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar), average across replicates, and write each descriptor to the system’s `/analysis` subdirectory using standard basenames.  
Compile all per‑system descriptors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram and heatmap (robust z‑score/IQR scaling) stored in a common results folder.  
Create a concise HTML report in `/reporter` that summarizes the clustering, displays the dendrogram/heatmap, provides brief literature context, and indicates a k=4 cut for interpretation while showing the full tree.  
All outputs must respect the specified directory structure and file naming conventions; no new simulations, preprocessing, or solvation steps should be invoked.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ne28_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
