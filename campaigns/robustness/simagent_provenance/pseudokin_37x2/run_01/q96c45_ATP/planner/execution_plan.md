# Planner Execution Plan

**Generated:** 2026-09-23 20:43:20
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting Goal (for q96c45_ATP):**  
1. Using the existing 200 ns production trajectories (two replicates) in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q96c45_ATP/`, compute the per‑trajectory and per‑system descriptors: ATP COM‑pocket distance (mean ± SD), ATP pocket‑axis angle (mean ± SD), pocket side‑chain χ₁ circular mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, and shared‑reference dihedral PCA entropy.  
2. Perform the requested analyses—ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF—on the full 200 ns trajectories, and save each result file in `/analysis/` using standard basenames (no label prefix).  
3. Assemble the ten scalar descriptors for all 37 systems into a single feature table, apply robust z‑score/IQR scaling, perform Ward hierarchical clustering, and generate a dendrogram and heatmap, writing both to `/analysis/`.  
4. Create a concise HTML report in `/reporter/` that includes: literature context, the full dendrogram + heatmap panel, a summary of the ten descriptors per system, and a brief interpretation (e.g., marking a k = 4 cut while preserving the complete tree).  
5. Ensure all outputs are produced without initiating any new preprocessing, simulation, or HPC steps—only use the already‑available trajectory data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q96c45_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
