# Planner Execution Plan

**Generated:** 2026-09-23 21:13:39
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal (analysis → reporter only)**  

1. **Analysis** – Load the two 200 ns MD replicas (`rep01.xtc`, `rep02.xtc`) from  
   `/home/akp66103/workspace/.../q9y243_ATP/` and compute, for each replicate and the 200 ns average, the following descriptors:  
   - ATP COM distance to the consensus pocket (mean & SD)  
   - ATP orientation vs. pocket axis (mean & SD of the axis angle)  
   - Pocket side‑chain χ₁ circular mean & SD  
   - Consensus‑mapped Cα RMSF mean & SD  
   - N‑lobe ↔ C‑lobe DCCM mean correlation  
   - Dihedral‑PCA landscape entropy (shared‑reference φ/ψ/χ₁ PCA)  
   - Additionally generate the per‑replicate ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, overall DCCM, dihedral PCA, nearby distances, and protein RMSF plots.  
   Output a single CSV table (`descriptors.csv`) and all plots with standard basenames in  
   `/home/.../q9y243_ATP/analysis/`.  

2. **Reporter** – Create a concise HTML report (`AKT3_Analysis_Report.html`) in  
   `/home/.../q9y243_ATP/reporter/` that presents the descriptor table, key plots, and a short literature context paragraph, noting that these metrics will be combined with the 36 other systems for downstream clustering.  

**Constraints** – Use the existing trajectories only; do not perform preprocessing, solvation, or new simulations. All analyses should follow the default physiological conditions (amber99sb-ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9y243_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
