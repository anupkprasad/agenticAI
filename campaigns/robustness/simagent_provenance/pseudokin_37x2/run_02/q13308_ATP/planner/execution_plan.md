# Planner Execution Plan

**Generated:** 2026-09-23 23:04:41
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal (analysis & reporter only)**  

1. Perform per‑system analyses on the already‑generated 200 ns production trajectories (two replicas each) for all 37 human protein–ATP holo structures, treating only the protein and ATP ligand as components (exclude crystallographic ions and waters).  
2. Compute the following metrics for each system (averaged over the two replicas):  
   - ATP COM distance to the consensus pocket (mean & SD)  
   - ATP orientation vs pocket axis (mean & SD of the axis angle)  
   - Pocket side‑chain χ₁ circular mean & SD  
   - Consensus‑mapped Cα RMSF mean & SD  
   - N‑lobe ↔ C‑lobe DCCM mean correlation  
   - Shared‑reference dihedral PCA dynamics scalar (pca_pka_ref_shared_dyn).  
   Also generate the specified per‑system analyses: ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, and protein RMSF.  
3. Compile the ten descriptors into a single feature table, run Ward hierarchical clustering, and generate a dendrogram plus a heat‑map panel (using robust z‑score/IQR scaling).  
4. Place all analysis files in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP/analysis/` and produce a concise HTML report (with literature context and optional k=4 cut) in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP/reporter/`.  
5. No preprocessing, simulation setup, or new trajectory generation is performed; the analysis strictly uses the existing simulation data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
