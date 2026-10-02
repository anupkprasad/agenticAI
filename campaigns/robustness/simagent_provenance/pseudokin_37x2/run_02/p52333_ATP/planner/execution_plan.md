# Planner Execution Plan

**Generated:** 2026-09-23 22:58:21
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting Task for the 37 protein‑ATP holo systems**

1. Using the existing 200‑ns trajectories (two independent replicas per system), perform the full set of analyses: compute ATP COM distance to the consensus pocket (mean and SD), ATP orientation vs pocket axis (mean and SD), pocket side‑chain χ₁ circular mean and SD, Cα RMSF of consensus‑mapped residues (mean and SD), N‑lobe ↔ C‑lobe DCCM mean correlation, and the shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar.  
2. For each system, average the metrics across the two replicas and record the ten required scalar descriptors in a per‑system feature table.  
3. Assemble all 37 feature tables into a single matrix, apply Ward hierarchical clustering, and generate a dendrogram and heat‑map panel (robust z‑score/IQR scaling) that includes a k = 4 cut for interpretation.  
4. Save all numeric outputs and plots in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP/analysis/` using standard basenames (no label prefixes).  
5. Produce a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP/reporter/` that summarizes the methodology, presents the dendrogram and heat‑map, lists the ten descriptors per system, and provides brief literature context for the clustering results.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
