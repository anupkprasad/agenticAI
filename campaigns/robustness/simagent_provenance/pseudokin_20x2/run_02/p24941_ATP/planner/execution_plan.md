# Planner Execution Plan

**Generated:** 2026-09-23 15:06:14
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the existing 200 ns trajectories for each of the 20 protein–ATP holo complexes (protein + ATP ligand, no crystallographic ions) and perform the following steps: 1) Map the consensus ATP‑binding pocket defined from the reference KAPCA (p17612) onto every system via MAFFT sequence alignment; 2) Compute the ten required scalar descriptors (ATP COM distance mean/std, ATP orientation mean/std, pocket χ₁ mean/std, consensus‑mapped Cα RMSF mean/std, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference φ/ψ/χ₁ dihedral PCA entropy) averaging over the two independent replicates per system and using the full 200 ns trajectory (no truncation); 3) Compile all descriptor values into a feature table; 4) Run Ward hierarchical clustering and generate a dendrogram and a robustly scaled feature‑heat‑map; 5) Produce a single combined HTML report with brief literature context.  
All analysis outputs should be stored in <working_dir>/analysis/ using standard basenames (no label prefix) and the final report should be placed in <working_dir>/reporter/.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p24941_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
