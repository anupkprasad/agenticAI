# Planner Execution Plan

**Generated:** 2026-09-23 23:38:16
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis & Reporter Only)**  

1. **Per‑system analysis**: For each of the 37 human protein‑ATP holo trajectories (two 200 ns replicas per system) located in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP/`, compute the ten dynamic descriptors:  
   • ATP COM distance to the consensus pocket (mean & SD)  
   • ATP orientation vs pocket axis (mean & SD of axis angle)  
   • Pocket side‑chain χ₁ circular mean & SD  
   • Consensus‑mapped Cα RMSF (mean & SD)  
   • N‑lobe ↔ C‑lobe DCCM mean correlation  
   • Shared‑reference φ/ψ/χ₁ dihedral‑PCA landscape entropy  
   Perform pocket mapping by aligning each protein to the KAPCA (p17612) pocket using a global MSA (MAFFT/star) and apply the same residue indices.

2. **Feature table & clustering**: Assemble the ten descriptors into a single feature matrix, apply robust z‑score/IQR scaling, and perform Ward hierarchical clustering. Produce a dendrogram and a feature‑heatmap panel in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP/analysis/`.  
   Include an optional k = 4 cut for interpretation but retain the full tree.

3. **HTML report**: Generate a concise HTML report in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP/reporter/` that summarizes the literature context, the clustering results, and key observations for each descriptor, using the standard basenames (no label prefixes) for all output files.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
