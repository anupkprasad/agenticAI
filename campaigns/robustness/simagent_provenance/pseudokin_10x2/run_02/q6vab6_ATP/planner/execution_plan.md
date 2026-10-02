# Planner Execution Plan

**Generated:** 2026-09-22 18:22:00
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis & reporter only)**

1. For each of the ten human protein‑ATP holo complexes (p17612:KAPCA, o60674:JAK2, p24941:CDK2, q8ivt5:KSR1, q13418:ILK, p00533:EGFR, p23458:JAK1, q6vab6:KSR2, q92519:TRIB2, q9y243:AKT3) that already have two 200 ns trajectories in their respective run directories, compute the following ten scalar descriptors from every replicate and then average across replicates:  
   • ATP COM‑pocket distance mean & SD  
   • ATP orientation vs pocket axis mean & SD  
   • Pocket side‑chain χ₁ circular mean & SD  
   • Consensus‑mapped Cα RMSF mean & SD  
   • N‑lobe ↔ C‑lobe DCCM mean correlation  
   • Shared‑reference dihedral PCA dynamics scalar (√(d_g² + d_c² + pc_rms²) relative to KAPCA)  

   Pocket residues are defined by the 15 Å ATP‑proximal shell of KAPCA and mapped onto the other proteins using a MAFFT global MSA.

2. Assemble all descriptors into a single feature table, apply Ward hierarchical clustering (full tree, robust z‑score/IQR scaling), and generate a dendrogram and heat‑map of the clustered features.

3. Write the descriptor table, clustering output, and visualizations to `<working‑dir>/analysis/` using standard basenames (no label prefixes).  
   Create a concise HTML report with a brief literature context and the dendrogram/heat‑map panel in `<working‑dir>/reporter/`.

4. Use only the protein, ATP ligand, and essential 0.15 M NaCl ions that were present in the existing trajectories; do not modify, re‑run, or re‑solvate the data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q6vab6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
