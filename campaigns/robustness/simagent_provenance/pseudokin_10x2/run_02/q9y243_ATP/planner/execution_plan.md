# Planner Execution Plan

**Generated:** 2026-09-22 18:38:46
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the existing 200‑ns production trajectories for all ten protein‑ATP holo complexes (p17612:KAPCA, o60674:JAK2, p24941:CDK2, q8ivt5:KSR1, q13418:ILK, p00533:EGFR, p23458:JAK1, q6vab6:KSR2, q92519:TRIB2, q9y243:AKT3) in their respective subdirectories.  
For each system compute ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF; then extract the ten required scalar descriptors (ATP COM distance mean/std, ATP orientation mean/std, pocket χ1 circular mean/std, consensus Cα RMSF mean/std, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral PCA dynamics scalar) by averaging over the two replicates.  
Compile these descriptors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram and feature‑heatmap with robust z‑score/IQR scaling (optionally mark a k = 4 cut).  
Store all analysis outputs under `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/analysis/` and produce a concise HTML report with brief literature context in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/reporter/`.  
All analyses must use the ATP ligand and pocket residues mapped from the KAPCA reference (p17612) and must exclude crystallographic Mg/ions.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q9y243_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
