# Planner Execution Plan

**Generated:** 2026-09-23 13:04:55
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporter Tasks**

1. **Analyze** the two 200 ns production trajectories (rep01/rep02) for each of the 20 protein–ATP holo complexes, computing the ten required scalar descriptors (ATP COM distance/angle, pocket χ₁ mean & SD, Cα RMSF mean & SD, N↔C DCCM mean, shared‑reference PCA scalar) for every frame and averaging the results across replicates.  
2. **Generate** full‑trajectory plots (200 ns) for each system, and for JAK2 (o60674) specifically produce an HTML report that includes the descriptor table, trajectory visualizations, and literature context.  
3. **Compile** a master descriptor matrix (20 × 10), apply robust z‑score / IQR scaling, perform Ward hierarchical clustering, and output a dendrogram (with k = 4 cut marked) and a feature‑heatmap panel.  
4. **Output** the following files: (i) per‑system descriptor CSVs and averaged values, (ii) a consolidated feature table (CSV), (iii) PNG/SVG plots for each trajectory, (iv) the dendrogram + heatmap image, and (v) a single combined HTML report containing all figures, tables, and a short literature review.  
5. **Constraints**: do not truncate trajectories, retain all ten descriptors, use the KAPCA‑defined consensus pocket (15 Å cutoff) mapped via MAFFT/MSA, and preserve the user‑specified component selections (protein + ligand, no crystallographic ions or waters).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o60674_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
