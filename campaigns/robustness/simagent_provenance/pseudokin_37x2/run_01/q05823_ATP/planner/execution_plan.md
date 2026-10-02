# Planner Execution Plan

**Generated:** 2026-09-23 19:33:21
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis & Reporter Agents**

1. Using the already‑generated 200 ns trajectories for q05823_ATP, perform all requested analyses (ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby, and protein RMSF) considering only the protein and ATP ligand components (exclude crystallographic ions and water).  
2. Compute the ten scalar descriptors (ATP‑COM distance mean / std, ATP‑axis orientation mean / std, pocket χ₁ circular mean / std, consensus‑Cα RMSF mean / std, N‑lobe ↔ C‑lobe DCCM mean, and dihedral‑PCA landscape entropy).  
3. Write all results to `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q05823_ATP/analysis/` using the standard basenames, then generate a concise HTML report summarizing the metrics and figures and place it in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q05823_ATP/reporter/`.  
4. Do not initiate any preprocessing, topology generation, HPC submission, or new simulation runs.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q05823_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
