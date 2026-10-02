# Planner Execution Plan

**Generated:** 2026-09-23 13:54:15
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased goal for the analysis → reporter workflow**  

1. Load the existing 200‑ns production trajectories for all 20 holo‑ATP systems (protein + ATP, no crystallographic Mg/ions).  
2. For each system, map the consensus ATP‑binding pocket (defined from KAPCA residues within 15 Å of ATP) onto the target using a global MAFFT alignment; compute the ten scalar descriptors (ATP COM distance & angle statistics, pocket χ₁ circular mean/SD, Cα RMSF mean/SD, N‑↔C DCCM mean, shared‑reference PCA scalar) from the two independent replicates and average them.  
3. Plot the full 200‑ns trajectories (distance, angle, RMSF, etc.) for each system without truncation.  
4. Assemble the 20‑row feature table, perform Ward hierarchical clustering, and generate a dendrogram + robustly scaled feature heatmap.  
5. Compile all results, visualizations, and a brief literature context into a single HTML report.  
6. No preprocessing, simulation setup, or new MD runs are performed; only the specified analysis and reporting steps are executed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p25092_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
