# Planner Execution Plan

**Generated:** 2026-09-23 13:23:22
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the two 200 ns production trajectories of the holo EGFR (p00533_ATP) stored in /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p00533_ATP.  
For each replicate compute the ten scalar dynamics descriptors: ATP COM distance and SD to the consensus pocket, ATP axis angle and SD, pocket side‑chain χ₁ mean and SD, Cα RMSF mean and SD for consensus‑mapped residues, N‑lobe ↔ C‑lobe DCCM mean, and the shared‑reference PCA dynamics scalar; then average the values across the two replicates.  
Generate full‑trajectory plots for the entire 200 ns of each run, assemble the descriptor table, and produce a single HTML report that includes the plots, descriptor summary, and brief literature context.  
The analysis should consider only the protein and ATP ligand (excluding crystallographic ions), using the existing TIP3P‑solvated, 0.15 M NaCl, 310 K, 1 bar system as provided.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p00533_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
