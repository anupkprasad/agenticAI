# Planner Execution Plan

**Generated:** 2026-09-23 19:49:11
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

1. For each of the 37 existing 200‑ns protein–ATP holo trajectories, perform the following analyses on the full time series: ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
2. Using the ATP‑binding pocket defined by the KAPCA reference (residues within 15 Å of ATP, mapped via global MSA to all systems), compute the ten scalar descriptors for every system:  
   • ATP COM distance to pocket (mean & std),  
   • ATP orientation vs pocket axis (mean & std of axis angle),  
   • Pocket side‑chain χ₁ (circular mean & std),  
   • Consensus‑mapped Cα RMSF (mean & std),  
   • N‑lob ↔ C‑lob DCCM mean correlation,  
   • Shared‑reference dihedral PCA landscape entropy.  
3. Aggregate the descriptor matrix for all 37 proteins, apply Ward hierarchical clustering, and produce a dendrogram plus a feature‑heatmap (robust z‑score/IQR scaling).  
4. Save all per‑system analysis files (CSV/JSON) under  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q58a45_ATP/analysis/`  
   and generate a concise HTML report (including literature context and a k = 4 cut‑off) in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q58a45_ATP/reporter/`.  
5. Do not reference preprocessing, simulation setup, HPC submission, or any new trajectory generation; use the existing production MD files only.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q58a45_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
