# Planner Execution Plan

**Generated:** 2026-09-22 17:14:00
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Goal (analysis + reporter)**  
Using the existing two 200‑ns production MD trajectories for the KSR2 holo complex (q6vab6_ATP) in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q6vab6_ATP`, compute the ten required scalar dynamics descriptors (mean / std of ATP COM distance to the consensus pocket, mean / std of ATP orientation vs pocket axis, pocket χ₁ circular mean / std, mean / std of RMSF of consensus‑mapped Cα atoms, mean correlation of N‑ and C‑lobe DCCM, and shared‑reference dihedral PCA scalar) for each replicate and then average across replicates. Generate the corresponding plots (distance vs time, orientation histogram, χ₁ circular plot, RMSF map, DCCM heatmap, PCA distance vs KAPCA) and compile a concise HTML report that includes these figures, a brief literature context for KSR2, and the full feature table (ready for future clustering). No preprocessing, simulation, or solvation steps are performed; analysis is limited to the provided trajectories.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q6vab6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
