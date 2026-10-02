# Planner Execution Plan

**Generated:** 2026-09-22 16:56:50
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis → reporter only)**  
1. Using the existing 200 ns trajectories for each of the ten protein–ATP holo structures, compute the ten scalar dynamics descriptors (ATP‑COM distance mean/SD, ATP‑pocket orientation mean/SD, pocket side‑chain χ₁ circular mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, shared‑reference φ/ψ/χ₁ dihedral PCA scalar).  
2. Define the ATP‑binding pocket from KAPCA (p17612) as residues within 15 Å of ATP, map this pocket onto the other proteins via a global MAFFT alignment, and use the mapped residues for the pocket‑centric metrics.  
3. Assemble the descriptor table, perform Ward hierarchical clustering with robust z‑score/IQR scaling, generate a dendrogram and feature‑heatmap, and produce an HTML report with plots and a brief literature context, marking a k = 4 cut for interpretation but presenting the full tree.  
4. All analyses must exclude crystallographic Mg/ions, include ATP, and use the default AMBER99SB‑ILDN/TIP3P/310 K/1 bar/0.15 M NaCl conditions.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p17612_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
