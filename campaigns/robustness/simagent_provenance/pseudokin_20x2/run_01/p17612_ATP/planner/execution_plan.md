# Planner Execution Plan

**Generated:** 2026-09-23 13:03:33
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting Goal**

1. For each of the 20 human protein–ATP holo structures (UniProt IDs listed), use the existing two 200‑ns GROMACS trajectory files (rep01 and rep02) and compute the ten required scalar descriptors (ATP COM distance/angle statistics, pocket χ₁ mean & SD, Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference PCA scalar).  
2. Map the ATP‑binding pocket of KAPCA (within 15 Å of ATP) onto the other proteins via a global MAFFT/MSA, and use this mapping for all pocket‑based calculations and for the Cα‑RMSF and DCCM analyses.  
3. Average each descriptor across the two replicates, plot the full 200‑ns trajectory of every system (no window truncation), and assemble the averaged ten descriptors into a single feature table.  
4. Perform Ward hierarchical clustering on the feature table, generate a dendrogram and robust (z‑score/IQR) feature‑heatmap (with a k = 4 cut suggested), and compile all plots, clustering output, and a concise literature context into a single HTML report.  
5. Exclude crystallographic Mg/ions from the source PDBs; include ATP as the ligand for all holo systems. No new preprocessing, simulation, or HPC steps are required—only the analysis and reporting stages.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p17612_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
