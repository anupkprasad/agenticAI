# Planner Execution Plan

**Generated:** 2026-09-22 18:19:26
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis & Reporter only)**  
1. Analyze the two existing 200‑ns trajectories for q13418_ATP, computing ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
2. For each replicate and the averaged data, calculate the ten family‑modular descriptors: (a) ATP COM distance to the consensus pocket (mean / SD), (b) pocket‑axis orientation (mean / SD of angle), (c) consensus Cα RMSF mean / SD, (d) pocket χ₁ circular mean / SD, (e) N‑lobe↔C‑lobe DCCM mean, and (f) dihedral‑PCA landscape entropy.  
3. Save all metrics as plain‑named CSV/TSV files in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q13418_ATP/analysis/` without any label prefixes.  
4. Produce a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q13418_ATP/reporter/` that includes plots, a feature table, and brief literature context.  
5. Do not run any new preprocessing, simulation, or equilibration steps; retain only the protein and ATP ligand (exclude crystallographic Mg/ions).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q13418_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
