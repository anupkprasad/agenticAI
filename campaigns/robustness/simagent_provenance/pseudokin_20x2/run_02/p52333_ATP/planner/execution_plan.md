# Planner Execution Plan

**Generated:** 2026-09-23 16:12:40
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporter Goal (20 human protein–ATP holo systems)**  

1. Using the already‑produced 200 ns trajectories (two 200 ns replicates per system), compute the ten scalar dynamics descriptors for each protein:  
   • ATP COM distance to the consensus pocket (mean & SD)  
   • ATP orientation vs pocket axis (mean & SD)  
   • Pocket side‑chain χ₁ circular mean & SD  
   • Consensus‑mapped Cα RMSF mean & SD  
   • N‑lobe ↔ C‑lobe DCCM mean correlation  
   • Shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar (pca_pka_ref_shared_dyn).  

2. Define the ATP‑binding pocket from KAPCA (p17612) as residues within 15 Å of ATP, map these pocket residues onto all other proteins via a global MSA, and use the mapped residues for all pocket‑based descriptors.

3. Average each descriptor across the two replicates per system, assemble all ten descriptors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust z‑score/IQR‑scaled feature‑heatmap panel.

4. Produce a single combined HTML report that includes the dendrogram, heatmap, the full feature table, and brief literature context for each protein.  

All analyses must use the protein‑with‑ligand (holo) configuration (protein + ATP + required ions), and no trajectory truncation is allowed. No preprocessing, simulation setup, or new simulation steps are to be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p52333_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
