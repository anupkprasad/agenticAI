# Planner Execution Plan

**Generated:** 2026-09-23 13:49:35
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the two 200‑ns replica trajectories that already exist for each of the 20 protein–ATP holo structures (including p21860). For every system, compute the ten scalar dynamics descriptors (ATP COM distance ± SD, ATP axis angle ± SD, pocket χ₁ circular mean ± SD, consensus‑mapped Cα RMSF mean ± SD, N‑lobe↔C‑lobe DCCM mean, shared‑reference PCA scalar) from both replicas, average the values, and generate full‑trajectory plots. Assemble the ten descriptors for all 20 systems into a single feature table, perform Ward hierarchical clustering, and produce a dendrogram plus a robustly scaled heatmap (robust z‑score/IQR). Compile all analyses, plots, and a brief literature context into one comprehensive HTML report, marking a k = 4 cut for interpretation. All work must use only the protein and ATP ligand from the PDB, explicitly exclude crystallographic Mg/ions, and rely solely on the existing 200‑ns trajectories—no additional preprocessing or new simulations may be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p21860_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
