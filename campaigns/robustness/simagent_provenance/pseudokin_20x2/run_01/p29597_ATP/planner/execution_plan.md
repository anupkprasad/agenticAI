# Planner Execution Plan

**Generated:** 2026-09-23 14:12:22
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis + Reporter only)**  

1. Using the existing two 200 ns trajectories of TYK2 (p29597) in /home/akp66103/.../p29597_ATP, analyze only the protein and ATP ligand atoms (ions and water excluded).  
2. Compute the ten scalar dynamics descriptors (ATP COM distance & SD to the consensus pocket, ATP axis angle & SD, pocket χ₁ mean & SD, Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference PCA dynamics scalar) for each replicate, then average across replicates.  
3. Generate plots of the full 200 ns trajectories (no truncation) and assemble the descriptor values into a table.  
4. Produce a comprehensive HTML report that presents the plots, the descriptor table, a brief literature context for TYK2, and a hierarchical clustering dendrogram with a k = 4 cut (full tree shown).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p29597_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
