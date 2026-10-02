# Planner Execution Plan

**Generated:** 2026-09-23 21:16:13
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis and Reporter Agents**

1. **Analysis** – For each of the 37 protein–ATP holo structures (case_id = protein_with_ligand, protein + ligand only, no ions, no water), load the two existing 200‑ns trajectories and compute:  
   * ATP COM distance to the consensus pocket (mean + std)  
   * ATP orientation vs the pocket axis (mean + std angle)  
   * Pocket side‑chain χ₁ circular mean + std  
   * Consensus‑mapped Cα RMSF mean + std  
   * N‑lobe ↔ C‑lobe DCCM mean correlation  
   * Dihedral‑PCA landscape entropy (pca_pka_ref_shared_dyn)  
   plus the standard per‑simulation analyses (ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF). Store all scalar results in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9y616_ATP/analysis/` using the canonical basenames (no prefixes).  
2. **Aggregation & Clustering** – Assemble the ten required descriptors from both replicates (averaged across replicates) into a single feature matrix, apply Ward hierarchical clustering, and generate a dendrogram (full tree) plus a feature‑heatmap (robust z‑score/IQR scaling).  
3. **Reporter** – Produce a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9y616_ATP/reporter/` that summarizes the clustering results, key statistics, and brief literature context. No preprocessing, simulation setup, or new trajectory generation is required; analysis is performed solely on the existing data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9y616_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
