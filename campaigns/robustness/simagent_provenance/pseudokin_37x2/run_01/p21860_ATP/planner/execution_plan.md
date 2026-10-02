# Planner Execution Plan

**Generated:** 2026-09-23 19:02:06
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

1. Analyze the already‑generated 200 ns trajectories for each of the 37 protein–ATP holo structures (protein + ATP, no crystallographic ions or water from the PDB).  
2. For every system, compute the ten required scalar descriptors: (i) mean & std of ATP COM distance to the consensus pocket, (ii) mean & std of ATP orientation vs the pocket axis, (iii) pocket side‑chain χ₁ circular mean & std, (iv) mean & std of consensus‑mapped Cα RMSF, (v) N‑lobe ↔ C‑lobe DCCM mean correlation, and (vi) shared‑reference dihedral PCA entropy.  
3. Generate per‑simulation plots for ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby residues, and protein RMSF, all covering the full 200 ns window.  
4. Assemble the 10‑descriptor feature table for all systems, perform Ward hierarchical clustering, and produce a dendrogram plus a feature‑heatmap (robust z‑score/IQR scaling).  
5. Compile a concise HTML report for each system (under `…/p21860_ATP/reporter/`) and a combined report with literature context, dendrogram, and heatmap, marking a k = 4 cut for interpretation but preserving the full tree.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p21860_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
