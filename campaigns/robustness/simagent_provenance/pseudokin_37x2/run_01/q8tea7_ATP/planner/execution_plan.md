# Planner Execution Plan

**Generated:** 2026-09-23 20:36:24
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal for the Analysis & Reporter Agents**

1. **Analysis** – For each of the 37 protein–ATP holo trajectories (already generated) perform the full set of per‑system analyses: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby residues, and protein RMSF. Extract the ten family‑modular descriptors: (i) ATP COM‑pocket distance mean and SD, (ii) ATP–pocket‑axis orientation mean and SD, (iii) pocket side‑chain χ₁ circular mean and SD, (iv) consensus‑mapped Cα RMSF mean and SD, (v) N‑lobe vs C‑lobe DCCM mean, and (vi) shared‑reference dihedral PCA landscape entropy. Save all outputs (numeric tables and plots) in the system’s `/analysis/` folder with standard basenames (no case label prefixes).

2. **Clustering & Report** – After all per‑system analyses are complete, compile the ten descriptor values for every system into a single feature matrix, perform Ward hierarchical clustering (full tree, optionally highlight a k = 4 cut), and generate a combined dendrogram + feature‑heatmap panel (robust z‑score/IQR scaling). Produce a concise HTML report for each system in `/reporter/` and a master HTML summary with literature context, the clustering figure, and key descriptor statistics. No new preprocessing, simulation setup, or trajectory generation steps should be invoked.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8tea7_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
