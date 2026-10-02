# Planner Execution Plan

**Generated:** 2026-09-24 00:21:18
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis → Reporter)**  

1. Using the already‑generated 200 ns production trajectories for each of the 37 human protein‑ATP holo structures, compute the requested per‑system descriptors: ATP COM distance to the consensus pocket (mean ± SD), ATP orientation vs pocket axis (mean ± SD), pocket side‑chain χ₁ circular mean ± SD, consensus‑mapped Cα RMSF mean ± SD, N‑lobe ↔ C‑lobe DCCM mean correlation, and the shared‑reference dihedral PCA dynamics scalar.  
2. Produce the additional analyses specified for each system—ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF—and store all results in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP/analysis/` using standard basenames (no label prefixes).  
3. Assemble the ten scalar descriptors for all 37 systems into a single feature table, apply robust z‑score/IQR scaling, and perform Ward hierarchical clustering.  
4. Output the complete dendrogram and a heatmap of the scaled feature matrix to the same analysis directory, and generate a concise HTML report—including literature context and a k = 4 cut interpretation—in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP/reporter/`.  
5. All analyses should use the holo (protein + ATP) configuration, excluding crystallographic ions and solvent that are not present in the source PDB, and adhere to the default simulation conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
