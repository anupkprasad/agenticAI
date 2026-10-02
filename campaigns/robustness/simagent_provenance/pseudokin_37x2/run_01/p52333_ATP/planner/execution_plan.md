# Planner Execution Plan

**Generated:** 2026-09-23 19:31:16
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the existing 200‑ns trajectories (rep01 and rep02) for all 37 protein–ATP holo structures (32 pseudokinases, 5 active kinases). For each trajectory extract the ten required scalar descriptors: mean and SD of ATP COM distance to the KAPCA‑defined consensus pocket; mean and SD of ATP orientation versus the pocket axis; circular mean and SD of pocket side‑chain χ₁; mean and SD of consensus‑mapped Cα RMSF; mean N‑lobe ↔ C‑lobe DCCM; and the shared‑reference dihedral PCA dynamics scalar. Assemble these descriptors into a single feature matrix, perform Ward hierarchical clustering, and generate a dendrogram plus a robustly scaled (z‑score/IQR) feature heatmap. Produce a concise HTML report (in the reporter directory) that includes literature context, the dendrogram, the heatmap, and a k = 4 cut interpretation. All analyses must use the full 200‑ns window and retain the ATP ligand while excluding crystallographic Mg/ions.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p52333_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
