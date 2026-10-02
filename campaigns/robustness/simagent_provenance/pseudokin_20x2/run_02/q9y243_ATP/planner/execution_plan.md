# Planner Execution Plan

**Generated:** 2026-09-23 15:42:08
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis & Reporter Workflow**

1. Analyze the two existing 200 ns MD trajectories for each of the 20 protein–ATP holo systems (PDBs in the working directory), extracting the ten required scalar dynamics descriptors (ATP COM distance mean/SD, ATP axis angle mean/SD, pocket χ₁ circular mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral PCA dynamics scalar).  
2. Map the ATP‑binding pocket of the reference KAPCA (p17612) onto every system using a MAFFT global sequence alignment, defining pocket residues as those within 15 Å of ATP in KAPCA; exclude crystallographic Mg/ions and any non‑ligand ions from the analysis.  
3. Average the descriptor values across the two replicates per system, assemble a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust‑scaled (z‑score/IQR) feature‑heatmap panel.  
4. Produce a combined HTML report in the `reporter/` sub‑folder that summarizes the clustering results, includes literature context for each kinase/pseudokinase, and embeds the dendrogram, heatmap, and per‑system descriptor tables.  
5. All analyses must be conducted on the pre‑existing trajectories; no preprocessing, simulation setup, or new MD runs are to be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q9y243_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
