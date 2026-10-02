# Planner Execution Plan

**Generated:** 2026-09-23 20:39:05
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis → Reporter Only)**  
1. For each of the 37 holo PDBs in the working directory, perform the full set of analysis tasks on the existing 200 ns trajectories: compute ligand‑pocket distance, consensus‑DCCM, consensus‑RMSF, consensus‑torsions, global DCCM, dihedral PCA, nearby‑atom contacts, and protein RMSF.  
2. Extract the ten family‑modular descriptors per system (ATP COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ circular mean/SD, consensus Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, dihedral PCA landscape entropy) using the ATP‑binding pocket defined by the KAPCA consensus (15 Å from ATP) and mapped onto each protein via a MAFFT global MSA.  
3. Store all analysis outputs in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q92519_ATP/analysis/` with standard basenames (no prefixes).  
4. Generate a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q92519_ATP/reporter/` that includes: (i) a dendrogram and feature‑heatmap of the compiled descriptor table (robust z‑score/IQR scaling, Ward clustering, k = 4 cut highlighted), and (ii) a brief literature context for the findings.  
5. Do not invoke any preprocessing, simulation setup, HPC submission, or trajectory generation steps; only analyze the existing data and produce the requested outputs.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q92519_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
