# Planner Execution Plan

**Generated:** 2026-09-23 23:34:01
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Analysis & Reporting Goal**

Using the already‑generated 200 ns trajectories for the 37 protein‑ATP holo structures (protein + ATP, ions excluded), perform the following for each system:

1. Identify the consensus ATP‑binding pocket (residues within 15 Å of ATP in KAPCA, mapped to other proteins via a global MAFFT MSA).  
2. Compute the ten required scalar descriptors (ATP COM distance mean/σ, ATP orientation mean/σ, pocket χ₁ mean/σ, consensus‑mapped Cα RMSF mean/σ, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA entropy) by averaging across the two replicas.  
3. Assemble all descriptors into a single feature table, apply robust z‑score/IQR scaling, perform Ward hierarchical clustering, and generate a full dendrogram and heatmap (k = 4 cut indicated for interpretation).  
4. Produce a concise HTML report in the reporter/ directory that presents the dendrogram, heatmap, key numerical results, and brief literature context, with outputs saved in the analysis/ directory under standard basenames (no label prefixes).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
