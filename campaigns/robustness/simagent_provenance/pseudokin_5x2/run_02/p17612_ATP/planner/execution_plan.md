# Planner Execution Plan

**Generated:** 2026-09-23 11:38:37
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Perform the analyses on the existing 200‑ns production trajectories for the five protein–ATP holo structures (p17612, o60674, p24941, q8ivt5, q13418). For each system compute the ten scalar descriptors: (1‑2) ATP COM distance to the consensus pocket (defined from the KAPCA reference, 15 Å from ATP) mean and std; (3‑4) ATP orientation versus the pocket axis mean and std; (5‑6) pocket side‑chain χ₁ circular mean and std; (7‑8) mean and std of RMSF for consensus‑mapped Cα atoms; (9) mean correlation of the N‑lobe ↔ C‑lobe DCCM; (10) shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar (pca_pka_ref_shared_dyn). Average the values over the two replicates per system and assemble them into a single feature table. Run Ward hierarchical clustering on this table, generate a dendrogram and a robust‑scaled heatmap (z‑score/IQR) in the /analysis/ directory, and produce a concise HTML report with the dendrogram, heatmap, literature context, and a k = 4 cut (but keep the full tree) in the /reporter/ directory. All outputs should use the standard basenames without label prefixes.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p17612_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
