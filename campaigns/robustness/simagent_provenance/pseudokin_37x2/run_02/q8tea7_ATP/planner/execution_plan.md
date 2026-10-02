# Planner Execution Plan

**Generated:** 2026-09-24 00:04:59
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Analysis‑Only Goal**

Analyze the two 200 ns production trajectories that already exist in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP`.  
For each replica compute the following descriptors: (1) ATP COM distance to the consensus pocket (mean and SD), (2) ATP orientation vs pocket axis (mean and SD), (3) pocket side‑chain χ₁ circular mean and SD, (4) consensus‑mapped Cα RMSF mean and SD, (5) N‑lobe vs C‑lobe DCCM mean correlation, and (6) shared‑reference dihedral PCA landscape entropy.  
Averages across the two replicas should be reported.  
Generate a Ward hierarchical clustering dendrogram, a robust‑z‑score/​IQR‑scaled heatmap of all descriptors, and a concise HTML report summarizing the results and providing a brief literature context for the TBCK holo complex.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
