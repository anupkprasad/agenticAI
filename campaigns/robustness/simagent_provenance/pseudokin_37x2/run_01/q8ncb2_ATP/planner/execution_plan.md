# Planner Execution Plan

**Generated:** 2026-09-23 20:25:52
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the q8ncb2_ATP System**

1. **Analysis**  
   - Using the existing 200‑ns production trajectories, compute:  
     * ligand pocket distance, consensus_DCCM, consensus_RMSF, consensus_torsions, DCCM, dihedral_PCA, nearby contacts, and protein RMSF.  
     * family‑modular descriptors: ATP COM distance to the consensus pocket (mean & SD), pocket‑axis orientation (mean & SD), consensus Cα RMSF mean & SD, pocket χ₁ circular mean & SD, N‑lobe ↔ C‑lobe DCCM mean, and dihedral PCA landscape entropy.  
   - Save all numeric results as CSVs, all plots (e.g., time series, correlation matrices, PCA scatter plots) in **/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ncb2_ATP/analysis/** with standard basenames (no case‑label prefix).

2. **Reporter**  
   - Generate a concise HTML report in **/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ncb2_ATP/reporter/** that:  
     * Summarizes the computed descriptors.  
     * Includes the key plots created in the analysis step.  
     * Provides brief literature context for CAMKV and its ATP binding behaviour.  

No additional preprocessing, simulation setup, or HPC execution steps are required; the analysis is performed on the already‑generated trajectories.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ncb2_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
