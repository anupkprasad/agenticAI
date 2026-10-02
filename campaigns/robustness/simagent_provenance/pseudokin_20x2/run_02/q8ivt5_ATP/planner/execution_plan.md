# Planner Execution Plan

**Generated:** 2026-09-23 15:03:30
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
For the 20 pre‑generated holo MD trajectories (two independent 200 ns replicates per system), perform the following analysis only:  

1. For each trajectory, compute the ten scalar descriptors (ATP COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral‑PCA entropy) using only the protein and ATP ligand (exclude crystallographic ions and waters).  
2. Map the ATP‑binding pocket defined by KAPCA (p17612) onto each protein via a global MAFFT alignment, and generate panels of the global MSA and the pocket/high‑consensus MSA.  
3. Average each descriptor over the two replicates per system, assemble all 20 systems into a single feature table, scale the data (robust z‑score/IQR), and perform Ward hierarchical clustering.  
4. Output a dendrogram and a feature‑heatmap panel (k=4 cut optional), and compile a combined HTML report that includes the descriptor table, clustering visualization, MSA panels, and brief literature context.  
All outputs should be written under the system‑specific directories: analysis/ and reporter/ as specified.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q8ivt5_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
