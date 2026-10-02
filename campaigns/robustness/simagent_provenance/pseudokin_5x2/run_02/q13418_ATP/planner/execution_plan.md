# Planner Execution Plan

**Generated:** 2026-09-23 11:51:06
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis & Reporter Agents**

For each of the five protein–ATP holo structures (p17612, o60674, p24941, q8ivt5, q13418) in the working directory, use the existing 200 ns production trajectories to:  

1. Compute the following per‑trajectory metrics – ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, global DCCM, dihedral PCA, nearby residues, and protein RMSF – and store them in `/analysis/` with standard basenames (no prefix).  
2. Extract the ten scalar descriptors (ATP‑COM distance mean/std, ATP‑pocket axis angle mean/std, pocket χ₁ mean/std, consensus‑mapped Cα RMSF mean/std, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA entropy) by averaging across the two 200 ns replicates for each system.  
3. Assemble these descriptors into a single feature table, apply Ward hierarchical clustering, and generate a dendrogram and feature‑heatmap (robust z‑score/IQR scaling) in `/reporter/`.  
4. Produce a concise HTML report in `/reporter/` that includes the clustering results, literature context, and a k = 4 cut‑off annotation, while retaining the full dendrogram.  

All analyses must respect the `protein_with_ligand` case (include ATP, exclude crystallographic Mg/ions). Trajectories are assumed already produced; no additional preprocessing, simulation setup, or HPC steps are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/q13418_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
