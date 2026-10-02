# Planner Execution Plan

**Generated:** 2026-09-22 18:24:29
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting Tasks (for all 10 holo complexes)**  
1. Load the two 200 ns production trajectories per system (no truncation).  
2. Run the following per‑trajectory analyses: ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
3. From the two replicates per system, compute the ten required scalar descriptors (ATP‑COM distance & std, ATP‑orientation angle & std, pocket χ₁ circular mean & std, Cα‑RMSF mean & std, N‑/C‑lobe DCCM mean, shared‑reference dihedral PCA distance).  
4. Aggregate these descriptors into a single feature table, apply Ward hierarchical clustering, and generate a dendrogram + robust‑z‑score heatmap (IQR scaling).  
5. Produce a concise HTML report (in `/home/.../reporter/`) summarizing the descriptors, clustering results, and literature context.  

All outputs (analysis files and report) should reside under the specified `analysis/` and `reporter/` directories, using standard basenames without labels. No new preprocessing or simulation steps are performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p23458_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
