# Planner Execution Plan

**Generated:** 2026-09-22 18:32:39
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
For each of the 10 holo‑ATP PDBs in /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02, analyze the already‑generated 200‑ns MD trajectories using the protein‑ligand (case_id protein_with_ligand) components (protein, ATP, required ions, no crystallographic Mg/ions).  
Compute the per‑trajectory metrics: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF, and from these derive the ten scalar descriptors (ATP COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ circular mean/SD, Cα RMSF mean/SD, N‑/C‑lobe DCCM mean, shared‑reference dihedral PCA dynamics scalar).  
Store each system’s results as a standardized‑basename file in …/analysis/; then merge all ten tables, perform Ward hierarchical clustering (full dendrogram, IQR‑scaled heatmap), and generate a single HTML report (with literature context) in …/reporter/.  
No new preprocessing, simulation, or HPC submission should be executed; only the existing trajectories are to be used.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q92519_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
