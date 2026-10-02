# Planner Execution Plan

**Generated:** 2026-09-23 11:39:32
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis & Reporter Agents**

1. For each of the five protein–ATP holo systems (p17612, o60674, p24941, q8ivt5, q13418), run the full GROMACS analysis suite on the existing 200 ns production trajectories (two independent replicates per system). Compute ligand‑pocket distances, consensus DCCM/RMSF/torsions, overall DCCM, dihedral PCA, nearby contacts, and protein RMSF, and save all output files in the respective `/analysis/` subdirectory using standard basenames (no label prefix).

2. Extract, for every system, the ten scalar dynamics descriptors—ATP COM distance mean and std, ATP orientation mean and std, pocket χ₁ circular mean and std, consensus‑mapped Cα RMSF mean and std, N‑lobe vs C‑lobe DCCM mean, and shared‑reference dihedral PCA landscape entropy—averaged across the two replicates.

3. Compile the descriptor matrix for all five systems, perform Ward hierarchical clustering, and generate a dendrogram plus a robust‑z‑score/IQR‑scaled feature‑heatmap. Produce a concise HTML report in the `/reporter/` directory that presents the dendrogram, heatmap, and brief literature context, clearly indicating the “protein_with_ligand” case (protein, ligand, and ions retained). No preprocessing, simulation setup, or HPC steps are included.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/o60674_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
