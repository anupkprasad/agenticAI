# Planner Execution Plan

**Generated:** 2026-09-24 00:13:24
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

1. For each of the 37 holo‑protein/ATP systems (including ULK4), use the existing 200 ns production trajectories from both replicas to compute the ten required scalar descriptors: ATP COM distance mean & SD, ATP orientation mean & SD, pocket side‑chain χ₁ circular mean & SD, consensus‑mapped Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean correlation, and the shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar.  
2. Aggregate these descriptors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram and robust‑scaled heatmap (z‑score/IQR) for all systems.  
3. Produce a concise HTML report in the `reporter/` directory that summarizes the clustering (highlighting a k=4 cut), includes the dendrogram and heatmap, and provides brief literature context for each protein family.  
4. Ensure only protein and ligand components are used; crystallographic Mg/ions are excluded.  
5. Do **not** run any new simulations, preprocessing, or setup steps—use the trajectories already present in the working directory.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
