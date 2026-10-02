# Planner Execution Plan

**Generated:** 2026-09-23 15:25:17
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis & Reporter Agents (only):**

1. For each of the 20 holo‐ATP protein trajectories (already available in their respective `/analysis/` directories), compute the ten scalar dynamics descriptors: ATP COM distance mean & SD, ATP orientation mean & SD, pocket χ₁ mean & SD, Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral PCA dynamics scalar.  
2. Define the consensus ATP‑binding pocket from KAPCA (p17612) using a 15 Å cutoff, map this pocket onto the other proteins via a global MAFFT MSA, and use the mapped residues for all descriptor calculations.  
3. Assemble all descriptors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust z‑score/IQR‑scaled feature‑heatmap panel.  
4. Produce a combined HTML report in each system’s `/reporter/` folder that includes the dendrogram, heatmap, literature context for each protein, and a k = 4 cut for interpretability (while preserving the full tree).  
5. Ensure no preprocessing, simulation setup, or HPC steps are mentioned or executed; analysis is limited to the existing 200 ns trajectories in full (no truncation).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p00533_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
