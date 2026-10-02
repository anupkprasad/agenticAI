# Planner Execution Plan

**Generated:** 2026-09-23 13:41:20
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the two 200‑ns replicates of the holo‑EPHB6 (o15197) trajectory stored in  
`/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o15197_ATP`.  
Compute the ten required scalar descriptors (ATP COM distance/angle, pocket χ₁ mean / SD, Cα RMSF mean / SD, N‑↔ C lobe DCCM mean, and shared‑reference PCA scalar) for each replicate, average the values across the two runs, and produce plots of the full 200‑ns trajectories (no window truncation).  
Generate an HTML report that includes the averaged descriptor table, trajectory visualizations, and a brief literature context for EPHB6.  
No additional preprocessing, simulation, or HPC steps are required; the analysis must be performed solely on the existing simulation data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o15197_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
