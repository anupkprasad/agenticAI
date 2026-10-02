# Planner Execution Plan

**Generated:** 2026-09-23 15:42:38
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis and Reporting Goal for /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/o15197_ATP**

1. Analyze the two existing 200 ns production trajectories (rep01 and rep02) for the holo ATP‑bound EPHB6 complex, extracting the ten required scalar dynamics descriptors (ATP COM distance, ATP–pocket axis angle, pocket χ₁ circular statistics, consensus‑mapped Cα RMSF, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral PCA distance) for each replicate and then averaging across replicates.  
2. Assemble the resulting ten descriptors for all 20 protein‑ATP holo systems into a single feature table, apply robust z‑score/IQR scaling, perform Ward hierarchical clustering, and generate a dendrogram and feature‑heatmap panel.  
3. Produce a combined HTML report (including literature context and a suggested k = 4 cut for interpretation) and write all analysis outputs to the `analysis/` subdirectory, placing the dendrogram and heatmap in `reporter/`.  
4. Ensure only the protein and ATP ligand are retained during preprocessing (ions and water excluded from the source PDB, but trajectories are solvated with TIP3P, 310 K, 1 bar, 0.15 M NaCl in a cubic box with 1.2 nm buffer, as per the default pipeline settings).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/o15197_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
