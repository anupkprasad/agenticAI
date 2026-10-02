# Planner Execution Plan

**Generated:** 2026-09-23 14:11:20
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the two existing 200‑ns production trajectories (rep01 and rep02) for the JAK3 holo complex (p52333_ATP) located in  
`/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p52333_ATP`.  
Compute the ten scalar dynamics descriptors (ATP COM distance/angle, pocket χ₁ mean & SD, Cα RMSF mean & SD, N‑↔C DCCM mean, shared‑reference PCA scalar) for each replicate, average the results, and output a feature table.  
Generate full‑trajectory plots for both replicates, assemble the average descriptors into a heat‑map, and produce a single HTML report that includes the plots, the feature table, and a brief literature context.  
The analysis must focus on the protein and ATP ligand only (crystallographic ions and any extra water from the source PDB are excluded, though the trajectories are solvated with TIP3P and 0.15 M NaCl under 310 K/1 bar).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p52333_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
