# Planner Execution Plan

**Generated:** 2026-09-24 00:27:37
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
For each of the 37 protein‑ATP holo structures, run the full set of trajectory analyses on the two 200 ns replicas (using only the protein and the ATP ligand, excluding any crystallographic ions). Compute the ten scalar descriptors per system by averaging over the two replicas: ATP COM distance mean and σ, ATP axis‑angle mean and σ, pocket side‑chain χ₁ circular mean and σ, consensus‑mapped Cα mean and σ RMSF, mean N‑lobe ↔ C‑lobe DCCM correlation, and shared‑reference dihedral PCA entropy. Assemble the resulting 37 × 10 feature matrix, perform Ward hierarchical clustering, and output a single dendrogram and a robust z‑score/IQR‑scaled heatmap. Store all analysis files in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP/analysis/` with standard basenames, and generate a concise HTML report—including the dendrogram, heatmap, and brief literature context—in the reporter directory `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP/reporter/`.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
