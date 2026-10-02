# Planner Execution Plan

**Generated:** 2026-09-23 20:08:32
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Using the 200‑ns trajectories already present in /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ivt5_ATP, perform the per‑simulation analyses (ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF) and extract the ten required scalar descriptors (ATP COM distance mean/σ, orientation mean/σ, pocket χ₁ mean/σ, Cα RMSF mean/σ, N‑/C‑lobe DCCM mean, dihedral PCA entropy). Compile these values into a single feature table, run Ward hierarchical clustering, and generate a dendrogram plus a robust‑scaled (z‑score/IQR) heatmap. Produce a concise HTML report summarizing the literature context, clustering results (including an optional k = 4 cut), and key descriptors, placing analysis outputs under /analysis/ and the report under /reporter/. No new preprocessing or simulation steps are performed; analysis is carried out solely on the existing trajectories.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ivt5_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
