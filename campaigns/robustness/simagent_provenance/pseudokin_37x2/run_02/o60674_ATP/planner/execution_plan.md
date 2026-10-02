# Planner Execution Plan

**Generated:** 2026-09-23 22:13:13
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal (Analysis → Reporter only)**  
1. For each of the 37 human protein‑ATP holo structures (UniProt IDs listed), use the already‑generated 200 ns GROMACS trajectories (two 200 ns replicas per system) to calculate the ten scalar descriptors: ATP‑COM distance (mean & SD), ATP orientation versus the pocket axis (mean & SD), pocket χ₁ circular mean & SD, consensus‑mapped Cα RMSF (mean & SD), N‑lobe ↔ C‑lobe DCCM mean correlation, and shared‑reference dihedral PCA scalar.  
2. Define the ATP‑binding pocket from KAPCA (p17612) as residues within 15 Å of ATP, map these residues onto every other protein via a global MAFFT MSA, and use the mapped residues to compute the pocket‑centric metrics.  
3. Assemble the ten descriptors into a single feature table, apply Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a dendrogram (showing full tree, optionally marking a k = 4 cut) and a feature heatmap.  
4. Create an HTML report summarizing the analysis, including literature context, in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP/reporter/`, while all intermediate outputs (feature table, clustering files, plots) are stored under the `analysis/` subdirectory.  
5. No new preprocessing, simulation setup, or trajectory generation is performed; only the existing trajectories are analyzed under the specified conditions.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
