# Planner Execution Plan

**Generated:** 2026-09-23 11:39:02
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis → Reporter Only)**  
1. Run the full set of requested analyses on the existing 200‑ns trajectories for **p24941_ATP** (protein + ATP, no crystallographic ions, no water from the PDB).  
   - Compute ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
   - For the ATP‑binding pocket (defined by the KAPCA reference), calculate the ATP COM‑pocket distance mean and SD, pocket‑axis orientation mean and SD, pocket side‑chain χ₁ circular mean and SD, consensus‑mapped Cα RMSF mean and SD, N‑lobe ↔ C‑lobe DCCM mean, and the shared‑reference dihedral PCA landscape entropy.  
2. Save all analysis outputs under  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p24941_ATP/analysis/`  
   using standard basenames (no label prefixes).  
3. Generate a concise HTML report summarizing the results and placing it in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p24941_ATP/reporter/`.  
4. Do **not** modify the trajectory files, parameters, or run any new simulations; focus exclusively on analysis and reporting.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p24941_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
