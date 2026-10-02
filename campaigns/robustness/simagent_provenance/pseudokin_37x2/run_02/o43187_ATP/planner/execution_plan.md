# Planner Execution Plan

**Generated:** 2026-09-23 22:14:04
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis and Reporter Agents**

1. **Analysis**  
   *For each of the 37 holo PDBs (protein + ATP only, no ions/water), use the two existing 200 ns GROMACS trajectories to compute the following ten scalar descriptors per system (average over both replicas):*  
   a) ATP COM distance to the consensus pocket (mean, SD)  
   b) ATP orientation relative to the pocket axis (mean angle, SD)  
   c) Pocket side‑chain χ₁ circular mean and SD  
   d) Consensus‑mapped Cα RMSF (mean, SD)  
   e) N‑lobe ↔ C‑lobe DCCM mean correlation  
   f) Shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar (as defined)  
   *Generate a feature table containing all ten descriptors for all 37 systems, perform Ward hierarchical clustering, and produce a dendrogram and robust z‑score/IQR‑scaled heatmap of the feature table.*

2. **Reporter**  
   *Create a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP/reporter/` that includes:*
   - Summary of the descriptor table and clustering results (with a k = 4 cut highlighted but full tree shown).  
   - Plots of the dendrogram and heatmap.  
   - Brief literature context on pseudokinase vs. active kinase behavior.  

*All analyses must use the standard physiological settings (amber99sb‑ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl) and the full 200 ns of each trajectory without truncation.*

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
