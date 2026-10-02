# Planner Execution Plan

**Generated:** 2026-09-23 23:36:07
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis and Reporting Goals for q8ivt5_ATP Workflow**

1. **Analysis**  
   *Process the existing 200 ns production trajectories for all 37 protein–ATP holo structures.*  
   - Compute the ten scalar dynamics descriptors for each system (ATP COM distance mean/SD, ATP axis angle mean/SD, pocket χ₁ mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA dynamics scalar).  
   - Generate per‑replicate and average values, then assemble a 37 × 10 feature table.  
   - Perform Ward hierarchical clustering on the feature table, produce a dendrogram and a robust‑scaled heatmap (z‑score/IQR).  
   - Prepare a concise HTML report summarizing the clustering, key metrics, and literature context.

2. **Reporter**  
   *Output the final analysis artifacts.*  
   - Store the feature table, dendrogram, heatmap, and HTML report in the directory  
     `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP/reporter/`.  
   - Ensure that all results reference the ATP ligand and the consensus pocket defined by KAPCA (p17612).  
   - No new simulations, preprocessing, or HPC submissions are to be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
