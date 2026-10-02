# Planner Execution Plan

**Generated:** 2026-09-24 00:38:44
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis & Reporter agents**

1. **Analysis** – Using the existing 200‑ns trajectories (two independent replicas per protein–ATP holo complex), compute the following ten scalar descriptors for each of the 37 systems (averaged over replicates):  
   a) Mean & SD of ATP COM distance to the consensus pocket (pocket defined from KAPCA within 15 Å of ATP, mapped onto other proteins via MAFFT sequence alignment);  
   b) Mean & SD of the ATP orientation angle relative to the pocket axis;  
   c) Circular mean & SD of pocket side‑chain χ₁ angles;  
   d) Mean & SD of consensus‑mapped Cα RMSF;  
   e) Mean correlation of the N‑lobe ↔ C‑lobe DCCM;  
   f) Shared‑reference dihedral PCA scalar (√(d_g² + d_c² + pc_rms²) in the shared PKA PC space).  
   Generate a feature table (rows: systems, columns: descriptors) and perform Ward hierarchical clustering, producing a dendrogram and a feature‑heatmap (robust z‑score/IQR scaling).  
2. **Reporter** – Compile the analysis outputs into a concise HTML report placed in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP/reporter/`. Include the dendrogram, heatmap, clustering interpretation (with an optional k=4 cut), and brief literature context linking the descriptors to pseudokinase vs. active kinase behavior.  

All analyses must consider the ligand (ATP) and protein only, exclude crystallographic ions and water, and use the full 200 ns production data without truncation.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
