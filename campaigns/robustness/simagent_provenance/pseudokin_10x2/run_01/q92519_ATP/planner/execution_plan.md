# Planner Execution Plan

**Generated:** 2026-09-22 17:23:07
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis & Reporter Only)**  

1. **Analysis** – From the existing two 200 ns trajectories of TRIB2‑ATP (protein + ligand, no Mg/ions), compute the ten required scalar descriptors (ATP‑COM distance mean & SD, ATP orientation mean & SD, pocket χ₁ circular mean & SD, consensus‑mapped Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA scalar). Process the full 200 ns window for each replicate, average the descriptors across the two runs, and generate the corresponding plots (distance histograms, orientation polar plots, χ₁ circular statistics, RMSF maps, DCCM heatmaps, PCA projection).  
2. **Reporter** – Assemble the descriptor table, produce a dendrogram + feature‑heatmap panel (Ward clustering, robust z‑score/IQR scaling), and create a single HTML report that includes the literature context, the plotted panels, and a brief interpretation (with a k = 4 cut highlighted).  

**Constraints** – Only the protein and ATP ligand are analyzed; crystallographic ions are excluded. All default simulation conditions (AMBER99SB‑ILDN, TIP3P, 310 K, 1 bar, 0.15 M NaCl, cubic box) apply only to the existing trajectories and are not altered. No preprocessing, simulation setup, or new MD runs are performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q92519_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
