# Planner Execution Plan

**Generated:** 2026-09-23 22:11:30
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis → reporter only)**  
1. For each of the 37 holo‑protein trajectories, extract the ATP‑binding pocket by mapping the 15‑Å residues around ATP in the KAPCA reference onto every system using a global MAFFT alignment.  
2. Compute the following per‑replicate metrics: ATP COM distance to the consensus pocket, ATP orientation versus pocket axis, pocket side‑chain χ₁ circular mean and std, consensus‑mapped Cα RMSF mean and std, N‑lobe↔C‑lobe DCCM mean, and shared‑reference φ/ψ/χ₁ dihedral PCA entropy; then average across the two 200‑ns replicas.  
3. Assemble the ten scalar descriptors into a feature table, perform Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a dendrogram and heatmap (include a k=4 cut line for interpretation).  
4. Write all analysis outputs to `/…/o15197_ATP/analysis/` (standard basenames, no prefix) and produce a concise HTML report in `/…/o15197_ATP/reporter/` that summarizes the results, provides the clustering visualization, and offers brief literature context.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
