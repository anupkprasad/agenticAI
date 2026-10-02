# Planner Execution Plan

**Generated:** 2026-09-23 22:28:06
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporter Workflow for the 37 protein–ATP holo systems**

1. **Analysis**: For each of the 37 holo PDBs (protein + ATP, no crystallographic Mg/ions) load the two existing 200 ns trajectories, then compute per‑trajectory the following ten scalar descriptors:  
   a) mean & SD of ATP COM distance to the consensus pocket,  
   b) mean & SD of ATP axis angle relative to the pocket axis,  
   c) circular mean & SD of pocket side‑chain χ₁,  
   d) mean & SD of Cα RMSF over consensus‑mapped residues,  
   e) mean N‑lobe ↔ C‑lobe DCCM correlation,  
   f) shared‑reference φ/ψ/χ₁ dihedral PCA entropy (pca_pka_ref_shared_dyn).  
   Aggregate across the two replicates to produce a single set of 10 values per system.  
   Also run the specified per‑system analyses (ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF) and store all outputs under  
   `/home/akp66103/workspace/.../p17612_ATP/analysis/` using standard basenames (no prefix).

2. **Reporter**: Assemble the 10‑column feature table for all 37 systems, apply robust z‑score/IQR scaling, perform Ward hierarchical clustering, and generate a dendrogram with a k = 4 cut highlighted. Create a heatmap of the scaled features.  
   Produce a concise HTML report in `/home/akp66103/workspace/.../p17612_ATP/reporter/` summarizing the clustering, key metrics, and literature context, and embed the dendrogram, heatmap, and individual analysis results.

All analyses assume the default physiological conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl, cubic box with 1.2 nm buffer) and include ATP as specified by the case_id `protein_with_ligand`. No new preprocessing, simulation setup, or trajectory generation is performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
