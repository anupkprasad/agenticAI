# Planner Execution Plan

**Generated:** 2026-09-23 13:01:48
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the two existing 200‑ns q8ivt5–ATP trajectories (rep01 and rep02) that contain only the protein and ATP (ions and crystallographic waters were omitted). Map the KAPCA consensus pocket (residues within 15 Å of ATP in KAPCA) onto q8ivt5 via a global MAFFT MSA, then compute the ten scalar dynamics descriptors for each replicate: ATP COM distance mean / SD, ATP orientation axis angle mean / SD, pocket side‑chain χ1 circular mean / SD, consensus‑mapped Cα RMSF mean / SD, N‑lobe↔C‑lobe DCCM mean, and the shared‑reference PCA scalar versus KAPCA. Average the descriptors across the two replicates, produce full‑trajectory plots for each run, and generate an HTML report containing the averaged descriptor table, plots, and brief literature context. No preprocessing, simulation setup, or new trajectory generation is required—only the analysis and reporting steps are to be executed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q8ivt5_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
