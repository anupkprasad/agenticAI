# Planner Execution Plan

**Generated:** 2026-09-23 21:10:27
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the existing 200‑ns production trajectories for all 37 protein–ATP holo complexes (protein + ATP only, excluding crystallographic ions and water) using the following per‑system analyses: ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby, and protein RMSF.  
Compute, for each system, the ten required scalar descriptors (ATP COM distance mean / std, pocket‑axis orientation mean / std, pocket χ₁ circular mean / std, consensus‑mapped Cα RMSF mean / std, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral‑PCA landscape entropy), averaging the two replicates.  
Compile these descriptors into a single CSV feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust z‑score/IQR‑scaled heatmap.  
Store all analysis outputs in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9c0k7_ATP/analysis/` and produce a concise HTML report (including literature context, dendrogram, heatmap, and summary tables) in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9c0k7_ATP/reporter/`.  
All analyses must use the consensus pocket defined by KAPCA (residues within 15 Å of ATP) mapped via MAFFT/MSA and must exclude crystallographic Mg/ions from the source PDBs.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9c0k7_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
