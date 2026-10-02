# Planner Execution Plan

**Generated:** 2026-09-23 23:50:50
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Using the 37 already‑generated 200 ns protein‑ATP trajectories (two replicas each) in /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP, compute for each system the ten dynamic descriptors: mean/std of ATP COM distance to the consensus pocket, mean/std of ATP orientation vs pocket axis, pocket χ₁ circular mean/std, mean/std of consensus‑mapped Cα RMSF, mean N‑lobe↔C‑lobe DCCM correlation, and shared‑reference dihedral‑PCA dynamics scalar. Assemble these descriptors into a feature table, run Ward hierarchical clustering, and generate a dendrogram and robust‑scaled heatmap in …/analysis/. Produce an HTML report in …/reporter/ summarizing the clustering, key metrics, literature context, and marking a k = 4 cut for interpretation. All analyses are limited to the holo (protein + ATP) structures; ions and water are retained as in the trajectories. Output files should use standard basenames without a label prefix.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
