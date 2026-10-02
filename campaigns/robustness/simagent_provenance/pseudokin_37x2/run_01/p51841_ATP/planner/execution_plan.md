# Planner Execution Plan

**Generated:** 2026-09-23 19:22:22
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the existing 200‑ns trajectories for each of the 37 protein–ATP holo structures (protein + ATP, no crystallographic ions). Compute the requested metrics: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF, and extract the ten scalar descriptors (ATP COM distance, ATP orientation, pocket χ₁ statistics, consensus Cα RMSF, N‑lobe ↔ C‑lobe DCCM, and shared‑reference dihedral PCA entropy). Assemble these descriptors into a single feature table, apply Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a dendrogram + heatmap. Output all analysis files to `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p51841_ATP/analysis/` using standard basenames, and create a concise HTML report summarizing the clustering, literature context, and key findings in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p51841_ATP/reporter/`. No new preprocessing, simulation setup, or trajectory generation should be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p51841_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
