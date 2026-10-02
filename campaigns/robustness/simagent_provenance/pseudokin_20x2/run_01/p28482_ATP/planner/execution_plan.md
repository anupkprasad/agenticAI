# Planner Execution Plan

**Generated:** 2026-09-23 13:59:54
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis → reporter)**  
1. Using the two existing 200 ns production trajectories in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p28482_ATP`, compute the ten scalar dynamics descriptors for every frame of each replicate (ATP COM distance & SD, ATP axis angle & SD, pocket χ₁ mean & SD, Cα RMSF mean & SD, N‑↔C lobe DCCM mean, shared‑reference PCA scalar).  
2. Average the descriptor values across the two replicates and plot the full 200 ns trajectories (including all residues, with the ATP‑binding pocket defined as residues within 15 Å of ATP in this structure).  
3. Generate a single HTML report that presents the averaged descriptor table, the full‑trajectory plots, and a concise literature context for the holo kinase MK01.  
4. Do not perform any preprocessing, simulation setup, or new MD runs; only analyze the provided trajectories and produce the requested report.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p28482_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
