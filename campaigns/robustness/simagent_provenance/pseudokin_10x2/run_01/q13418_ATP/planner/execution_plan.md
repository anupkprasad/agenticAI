# Planner Execution Plan

**Generated:** 2026-09-22 17:09:58
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the already‑generated 200 ns production trajectories for all ten protein–ATP holo structures (p17612, o60674, p24941, q8ivt5, q13418, p00533, p23458, q6vab6, q92519, q9y243). For each system and each of the two replicates, compute the ten scalar dynamics descriptors (ATP COM distance mean & SD, ATP orientation mean & SD, pocket χ1 circular mean & SD, mean & SD of consensus‑mapped Cα RMSF, N‑lobe↔C‑lobe DCCM mean correlation, shared‑reference dihedral PCA scalar). Average the descriptors across the two replicates, assemble them into a single feature table, run Ward hierarchical clustering, and generate a dendrogram and feature‑heatmap (robust z‑score/IQR scaling). Produce a combined HTML report that includes all plots, the feature table, the dendrogram, the heatmap, and a brief literature context. Focus only on the protein and ATP ligand components (exclude crystallographic Mg/ions), and treat the trajectories as already simulated under the standard AMBER99SB‑ILDN/TIP3P, 310 K, 1 bar, 0.15 M NaCl conditions.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q13418_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
