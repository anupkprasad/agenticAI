# Planner Execution Plan

**Generated:** 2026-09-23 14:12:50
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis → Reporter)**  

1. In the directory `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q05823_ATP`, analyze the two existing 200‑ns MD replicates of the q05823–ATP holo complex.  
2. Restrict all calculations to the protein and ATP ligand atoms (exclude crystallographic Mg/ions, other ions, and water).  
3. Compute the ten required scalar descriptors (ATP COM distance/angle statistics, pocket χ₁ mean & SD, Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference PCA scalar) for each replicate, then average the values across the two runs.  
4. Generate full‑trajectory plots (200 ns, no truncation) for both replicates and produce an HTML report that presents the descriptor table, trajectory visualizations, and a brief literature context for the holo kinase RN5A.  
5. No new preprocessing, simulation setup, or trajectory generation is required; only the analysis and reporting steps will be executed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q05823_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
