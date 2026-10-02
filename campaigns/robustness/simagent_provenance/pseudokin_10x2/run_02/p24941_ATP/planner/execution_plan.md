# Planner Execution Plan

**Generated:** 2026-09-22 18:04:42
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal (Analysis → Reporter only)**  
For each of the 10 protein‑ATP holo systems (p17612–p23458, q6vab6, q92519, q9y243) that already contain their 200 ns production trajectories, run the full set of analyses: ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, and protein RMSF, focusing exclusively on the protein and ATP ligand (exclude ions and water). Compute the ten scalar dynamics descriptors (ATP COM distance statistics, ATP–pocket orientation statistics, pocket χ₁ mean and SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral‑PCA scalar) for each system, using the KAPCA (p17612) pocket (≤15 Å from ATP) as the consensus reference mapped via global sequence alignment. Assemble these descriptors into a single feature table, perform Ward hierarchical clustering (retaining the full tree) and generate a dendrogram plus a feature‑heatmap panel (robust z‑score/IQR scaling). Output all per‑system analysis files under `/…/p24941_ATP/analysis/` with standard basenames (no label prefixes) and produce a concise HTML report, including literature context and the clustering results, in `/…/p24941_ATP/reporter/`. No new preprocessing, simulation setup, or trajectory generation should occur.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p24941_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
