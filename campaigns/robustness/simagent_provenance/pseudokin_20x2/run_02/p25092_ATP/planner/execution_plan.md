# Planner Execution Plan

**Generated:** 2026-09-23 15:56:02
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
1. For each of the 20 protein‑ATP holo PDBs in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/`, load the two existing 200 ns MD trajectories (full length, no truncation).  
2. Using the KAPCA (p17612) holo complex as reference, identify the ATP‑binding pocket (residues within 15 Å of ATP), map these residues onto each system via a global MAFFT alignment, and compute the ten scalar dynamics descriptors per system (mean & SD of ATP COM distance to pocket, mean & SD of ATP‑pocket axis angle, pocket χ₁ circular mean & SD, mean & SD of Cα RMSF of mapped residues, N‑lobe ↔ C‑lobe DCCM mean correlation, and shared‑reference dihedral‑PCA dynamics scalar). Average each descriptor over the two replicates.  
3. Assemble all ten descriptors into a single feature table, apply Ward hierarchical clustering, and generate a dendrogram plus an IQR‑scaled feature‑heatmap panel.  
4. Export the feature table, dendrogram, heatmap, and a concise HTML report (including brief literature context) to `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p25092_ATP/analysis/` and `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p25092_ATP/reporter/`, using standard basenames (no label prefix).  
5. Ensure only the protein and ligand atoms are considered in the descriptor calculations, while the trajectories themselves contain the full solvated system (water and NaCl).  
6. Do not perform any preprocessing, simulation setup, or new MD runs; focus exclusively on analysis of the existing trajectories and reporting.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p25092_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
