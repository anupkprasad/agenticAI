# Planner Execution Plan

**Generated:** 2026-09-22 16:56:47
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis & Reporting**

1. Using the two existing 200‑ns production MD trajectories for p24941_ATP (protein+ATP, no crystallographic ions or water), compute the ten required scalar dynamics descriptors:  
   - Mean & SD of ATP COM distance to the consensus pocket;  
   - Mean & SD of ATP orientation angle relative to the pocket axis;  
   - Circular mean & SD of pocket side‑chain χ₁ angles;  
   - Mean & SD of RMSF of consensus‑mapped Cα atoms;  
   - Mean DCCM correlation between N‑lobe and C‑lobe Cαs;  
   - Shared‑reference φ/ψ/χ₁ dihedral PCA scalar (pca_pka_ref_shared_dyn).  
   Average each descriptor over the two replicates.

2. Generate plots for each descriptor across the full 200‑ns trajectory (no truncation).

3. Assemble the ten descriptor values into a feature table, perform Ward hierarchical clustering, and create a combined dendrogram + feature‑heatmap panel using robust z‑score/IQR scaling (indicate a k=4 cut for interpretation but display the full tree).

4. Produce a single HTML report that includes the plots, the clustering figures, a concise literature context for CDK2/ATP interactions, and a summary of the descriptor table.

All analyses should be conducted on the already‑generated trajectories; no additional preprocessing, simulation setup, or HPC job submissions are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p24941_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
