# Planner Execution Plan

**Generated:** 2026-09-22 17:17:06
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the JAK1 Holo Complex (analysis → reporter only):**  

1. **Analysis** – Using the two 200 ns production trajectories already present in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p23458_ATP`, compute the ten scalar dynamics descriptors defined for the ATP‑binding pocket (ATP COM distance mean & SD, ATP orientation mean & SD, pocket χ₁ circular mean & SD, mean & SD of RMSF for consensus‑mapped Cα atoms, N‑lobe ↔ C‑lobe DCCM mean correlation, and shared‑reference φ/ψ/χ₁ dihedral PCA scalar).  
   *Map the KAPCA pocket (residues within 15 Å of ATP) onto JAK1 via a MAFFT MSA; use the resulting consensus‑mapped residues for the pocket‑centric metrics.*  
   *Average the descriptors across the two independent replicates and produce a single descriptor table for JAK1.*  

2. **Reporter** – Generate the following outputs:  
   * Plots for each descriptor (e.g., time‑series, histograms, angle distributions).  
   * A dendrogram and feature‑heatmap panel (using Ward hierarchical clustering, robust z‑score/IQR scaling) that includes JAK1’s descriptor vector (the full tree will be expanded later when other systems are processed).  
   * A combined HTML report containing the descriptor table, plots, clustering panel, and brief literature context; mark a k = 4 cut on the dendrogram for interpretation but retain the complete tree.  

All analysis must use the AMBER99SB‑ILDN force field, TIP3P water, 310 K, 1 bar, 0.15 M NaCl conditions (already satisfied in the existing trajectories). No new preprocessing, simulation, or HPC steps are to be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p23458_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
