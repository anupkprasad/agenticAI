# Planner Execution Plan

**Generated:** 2026-09-24 00:06:32
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis and Reporter Agents**

Analyze the two 200‑ns MD replicas already produced for each of the 37 protein‑ATP holo structures (case_id = protein_with_ligand, ligand = ATP, ions excluded). For every system, compute the following descriptors from the full 200‑ns trajectories: ATP COM distance to the consensus pocket (mean, std), ATP orientation vs pocket axis (mean, std), pocket side‑chain χ₁ mean and std, consensus‑mapped Cα RMSF mean and std, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference φ/ψ/χ₁ dihedral PCA scalar. Generate per‑system analyses for ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, and protein RMSF. Assemble all ten descriptors into a single feature table, perform Ward hierarchical clustering, and output a dendrogram and heatmap (robust z‑score/IQR scaling) in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP/analysis/`. Finally, create a concise HTML report summarizing the results, literature context, and a k = 4 cut interpretation, placing it in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP/reporter/`. No preprocessing, simulation, or solvation steps are to be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
