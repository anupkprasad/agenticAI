# Planner Execution Plan

**Generated:** 2026-09-23 19:49:14
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporter Goal (for q5jzy3_ATP):**  
1. Using the already‑generated two 200 ns trajectories, compute the per‑replicate metrics: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, global DCCM, dihedral PCA, nearby residues, and protein RMSF, then average across replicates.  
2. From these results extract the ten required descriptors (ATP COM distance mean & SD, ATP orientation mean & SD, pocket χ₁ circular mean & SD, Cα RMSF mean & SD, N‑/C‑lobe DCCM mean, dihedral PCA‑entropy).  
3. Assemble the descriptors from all 37 holo systems into a feature matrix, apply Ward hierarchical clustering, and generate a dendrogram + robust z‑score/IQR heatmap.  
4. Produce a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q5jzy3_ATP/reporter/` summarizing the descriptors, clustering, and brief literature context.  

All analyses must use the protein+ATP ligand component only (ions and waters are part of the trajectories but excluded from component extraction). No preprocessing, simulation setup, or new simulations are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q5jzy3_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
