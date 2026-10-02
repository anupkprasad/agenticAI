# Planner Execution Plan

**Generated:** 2026-09-23 23:55:33
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Using the existing 200 ns production trajectories from the two independent replicas for each of the 37 protein‑ATP holo structures, perform the full set of post‑processing analyses: ligand pocket distance (ATP COM to consensus pocket), ligand orientation vs pocket axis, pocket side‑chain χ₁ statistics, consensus Cα RMSF, N‑lobe vs C‑lobe DCCM, shared‑reference φ/ψ/χ₁ dihedral PCA, and any other required metrics (consensus_dccm, consensus_rmsf, consensus_torsions, nearby, protein RMSF). For each system compute the ten scalar descriptors (mean/std of ATP COM distance, mean/std of axis angle, circular mean/std of pocket χ₁, mean/std of consensus Cα RMSF, mean N‑lobe↔C‑lobe DCCM, shared‑reference dihedral PCA entropy), average across the two replicas, and assemble them into a single feature table. Apply Ward hierarchical clustering to the standardized feature table, generate a dendrogram and heatmap (robust z‑score/IQR scaling), and cut the tree at k = 4 for interpretative labeling while preserving the full tree. Produce an HTML report in the reporter directory that includes literature context, the global and pocket MSA panels mapped via KAPCA, the clustering visualization, and concise interpretations of the results. Store all analysis outputs (feature table, clustering dendrogram, heatmap, MSA panels, and report) under the analysis and reporter subdirectories of the working directory, without invoking any new preprocessing or simulation steps.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
