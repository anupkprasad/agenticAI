# Planner Execution Plan

**Generated:** 2026-09-24 00:38:40
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Perform the full analytical workflow for the 37 existing holo‑ATP trajectories in  
`/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP/`.  
For each system (protein + ATP, excluding crystallographic ions and solvent) compute the ten scalar descriptors: mean/SD of ATP COM distance to the consensus pocket, mean/SD of ATP orientation vs pocket axis, circular mean/SD of pocket χ₁, mean/SD of Cα RMSF of consensus‑mapped residues, mean N‑lobe ↔ C‑lobe DCCM correlation, and shared‑reference dihedral PCA entropy.  
Aggregate the descriptors across the two 200 ns replicas (average per system), assemble a feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust‑scaled heatmap.  
Save all individual‑system analyses (JSON/CSV) in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP/analysis/` and produce a single HTML report with literature context, the clustering diagram, and the heatmap in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP/reporter/`.  
No preprocessing, simulation setup, or new trajectory generation is required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
