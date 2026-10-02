# Planner Execution Plan

**Generated:** 2026-09-23 19:20:56
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal (analysis → reporter)**  

1. For each of the 37 protein–ATP holo trajectories already present in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p28482_ATP/analysis/`, perform the requested analyses: ligand‑pocket distance, consensus‑DCCM, consensus‑RMSF, consensus‑torsions, full‑trajectory DCCM, dihedral PCA, nearby residues, and protein‑RMSF.  
2. From these analyses compute the ten family‑modular descriptors (ATP‑COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ circular mean/SD, consensus Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, dihedral‑PCA landscape entropy) using the ATP‑binding pocket defined by residues within 15 Å of ATP and mapped via MAFFT alignment to KAPCA.  
3. Assemble all ten descriptors into a single feature table, run Ward hierarchical clustering, and generate a dendrogram and robust z‑score/IQR‑scaled heatmap, saving the plots to the analysis directory.  
4. In `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p28482_ATP/reporter/`, produce a concise HTML report that includes the clustering interpretation (highlighting a k = 4 cut), the descriptor table, literature context for each protein, and links to the plots.  
5. All outputs must use standard basenames (no label prefixes) and must not truncate trajectories (use full 200 ns). No new simulations, preprocessing, or HPC submissions should be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p28482_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
