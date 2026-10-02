# Planner Execution Plan

**Generated:** 2026-09-23 23:50:53
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

Perform the full suite of post‑processing analyses for the 37 human protein–ATP holo structures, using only the existing 200 ns trajectories (two replicas per system). For each system, extract the ten scalar dynamics descriptors (ATP‑COM distance mean/SD, ATP‑pocket orientation mean/SD, pocket χ₁ circular mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral‑PCA dynamics scalar) by mapping the ATP‑binding pocket from KAPCA (p17612) via MAFFT/MSA, and by excluding any crystallographic Mg/ions while retaining the ligand. Aggregate the descriptors into a feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust‑scaled heatmap, all saved under `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP/analysis/` with standard basenames. Finally, compile a concise HTML report, including literature context and a k = 4 cut‑tree annotation, under `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP/reporter/`. No preprocessing, simulation setup, or new trajectory generation will be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
