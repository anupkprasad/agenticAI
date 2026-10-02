# Planner Execution Plan

**Generated:** 2026-09-24 00:43:23
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Using the already‑generated 200 ns production trajectories for the 37 holo structures (protein + ATP, no crystallographic ions), compute for each system the ten required scalar descriptors: (1) mean and SD of the ATP COM distance to the consensus pocket (defined from KAPCA), (2) mean and SD of the ATP orientation angle relative to the pocket axis, (3) pocket side‑chain χ₁ circular mean and SD, (4) mean and SD of Cα RMSF for consensus‑mapped residues, (5) mean N‑lobe ↔ C‑lobe DCCM correlation, and (6) the shared‑reference φ/ψ/χ₁ dihedral PCA dynamic scalar. Average these descriptors across the two independent replicas for each protein, assemble them into a feature table, standardize (robust z‑score/IQR), and perform Ward hierarchical clustering; output the full dendrogram and a heatmap to **/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP/analysis/** using standard basenames.  
Generate a concise HTML report in **/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP/reporter/** that presents the dendrogram, heatmap, a brief literature context, and a k = 4 cut for interpretation. No preprocessing, simulation setup, or new trajectory generation should be performed—only analysis and reporting are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
