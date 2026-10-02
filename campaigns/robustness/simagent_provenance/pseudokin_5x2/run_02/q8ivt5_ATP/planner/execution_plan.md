# Planner Execution Plan

**Generated:** 2026-09-23 11:36:28
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis → reporter only)**  
1. Use the already‑produced two 200 ns production trajectories for each of the five protein–ATP holo complexes (KAPCA, JAK2, CDK2, KSR1, ILK).  
2. Compute the following per‑trajectory analyses: ligand pocket distance (ATP COM to the KAPCA‑defined consensus pocket), consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby, and protein RMSF.  
3. From the two replicates, extract and average the ten required scalar descriptors (ATP COM distance mean/std, pocket‑axis angle mean/std, χ₁ circular mean/std, consensus‑mapped Cα RMSF mean/std, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA entropy).  
4. Assemble all descriptors into a single feature table, run Ward hierarchical clustering, and generate a dendrogram plus robustly scaled heat‑map (z‑score/IQR).  
5. Produce concise HTML reports for each simulation in /…/q8ivt5_ATP/reporter/ and a combined HTML report (with literature context) in /…/q8ivt5_ATP/reporter/; place all raw analysis outputs under /…/q8ivt5_ATP/analysis/ using standard basenames (no label prefixes).  
6. Do not perform any preprocessing, simulation setup, or new trajectory generation—use only the existing data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/q8ivt5_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
