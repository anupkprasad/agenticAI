# Planner Execution Plan

**Generated:** 2026-09-23 15:24:08
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis Goal (per system)**  
For each of the 20 protein–ATP holo structures (including the ATP ligand and excluding crystallographic Mg/ions and water), analyze the two existing 200 ns MD trajectories in full. Compute the ten scalar dynamics descriptors (ATP COM distance mean & SD, ATP–pocket axis mean & SD, pocket χ₁ circular mean & SD, consensus‑mapped Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral PCA dynamics scalar) by averaging across the two replicates. Assemble all descriptors into a single feature table, apply Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a dendrogram and a feature‑heatmap panel. Finally, produce a consolidated HTML report in the reporter/ directory that includes the dendrogram, heatmap, clustering interpretation (suggesting k = 4 if appropriate), and concise literature context. All outputs should reside in the specified analysis/ and reporter/ sub‑folders under the working directory.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q6vab6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
