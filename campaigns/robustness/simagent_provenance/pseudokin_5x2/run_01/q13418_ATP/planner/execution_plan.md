# Planner Execution Plan

**Generated:** 2026-09-23 11:07:23
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the two 200‑ns replicates for each of the five holo PDBs (p17612, o60674, p24941, q8ivt5, q13418). For each trajectory compute the ten scalar descriptors listed (ATP COM distance and orientation statistics, pocket χ₁ circular mean/std, consensus‑mapped Cα RMSF mean/std, N‑lobe/C‑lobe DCCM mean, and shared‑reference dihedral PCA dynamics scalar). Average each descriptor over the two replicates per system, assemble a feature table, and perform Ward hierarchical clustering. Produce a dendrogram and heatmap (robust z‑score/IQR scaling) and a single HTML report with literature context and a k = 4 cut for interpretation. Store analysis outputs in the workspace’s /analysis/ directory with standard basenames and the report in /reporter/, honoring the case_id protein_with_ligand. The ATP‑binding pocket defined by KAPCA (p17612) within 15 Å of ATP should be mapped onto the other proteins via a global MAFFT/star MSA, and all descriptors must be calculated relative to this consensus pocket.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/q13418_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
