# Planner Execution Plan

**Generated:** 2026-09-23 16:06:22
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
For each of the 20 protein‑ATP holo complexes already present in the working directory, use the two existing 200‑ns MD trajectories per system to: (1) define the consensus ATP‑binding pocket from the KAPCA (p17612) reference (residues within 15 Å of ATP) and map it onto the other proteins via a global MSA; (2) compute the ten scalar dynamics descriptors (ATP COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe/C‑lobe DCCM mean, and shared‑reference dihedral PCA entropy) by averaging across the two replicates; (3) assemble a single feature table (one row per protein) in the analysis/ subdirectory; (4) perform Ward hierarchical clustering on the standardized features, and generate a dendrogram and robust z‑score/IQR‑scaled feature‑heatmap, saving the plots in analysis/; (5) produce a combined HTML report in reporter/ that includes the clustering figures, a brief literature context for each protein, and a concise summary of the analysis. No additional preprocessing, simulation, or HPC steps are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p51841_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
