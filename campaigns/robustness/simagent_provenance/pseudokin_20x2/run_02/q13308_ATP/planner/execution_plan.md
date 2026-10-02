# Planner Execution Plan

**Generated:** 2026-09-23 16:21:50
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased goal (analysis → reporter only)**  
1. Using the already‑produced 200 ns trajectories for the 20 protein‑ATP holo complexes, compute the ten required scalar dynamics descriptors (mean and SD for ATP‑COM distance, ATP‑pocket orientation, pocket χ₁ mean/SD, consensus Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, and the shared‑reference dihedral‑PCA dynamics scalar) for each of the two independent replicates, then average across replicates.  
2. Perform the additional per‑system analyses requested (ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby, protein RMSF) on the full 200 ns trajectories, excluding any crystallographic Mg/ions and retaining only the ATP ligand.  
3. Assemble a single feature table from the averaged descriptors, apply Ward hierarchical clustering with robust z‑score/IQR scaling, and output a dendrogram plus a feature‑heatmap panel.  
4. Generate a combined HTML report (in the specified reporter directory) that includes the dendrogram, heatmap, and a brief literature context for each protein, with the KAPCA (p17612) pocket used as the reference for mapping and descriptor calculation.  
5. All results must be saved under the analysis and reporter subdirectories of the working directory, using standard basenames (no label prefixes).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q13308_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
