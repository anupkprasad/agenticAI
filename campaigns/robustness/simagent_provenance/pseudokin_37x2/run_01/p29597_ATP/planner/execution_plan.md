# Planner Execution Plan

**Generated:** 2026-09-23 19:31:21
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
1. For every pre‑existing trajectory of the 37 protein–ATP holo systems (two 200 ns replicates each), run the full set of requested analyses (ligand‑pocket distance, consensus DCCM/RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, protein RMSF).  
2. From the results, compute the ten scalar descriptors (ATP‑COM distance mean / sd, ATP‑pocket axis angle mean / sd, pocket χ₁ circular mean / sd, consensus‑Cα RMSF mean / sd, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral PCA entropy) per system and average over the two replicates.  
3. Assemble all ten descriptors into a single feature table, apply Ward hierarchical clustering, and output a dendrogram + robust z‑score/IQR heatmap.  
4. Generate a concise HTML report (under `/…/p29597_ATP/reporter/`) summarizing each system’s descriptors, the clustering dendrogram, the heatmap, and a brief literature context.  
5. All analyses must focus only on the protein and ATP ligand (exclude ions and water); no new simulation or preprocessing steps are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p29597_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
