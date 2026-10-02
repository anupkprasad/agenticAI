# Planner Execution Plan

**Generated:** 2026-09-23 10:54:47
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting Goal (for the p24941_ATP directory)**  

1. **Analysis** – Load the two existing 200 ns production trajectories for each of the five holo systems (p17612, o60674, p24941, q8ivt5, q13418).  
   * Map the ATP‑binding pocket defined by KAPCA (residues ≤15 Å from ATP) onto each protein via a global MAFFT MSA.  
   * For every trajectory, compute the ten required scalar descriptors (ATP COM distance mean/SD, ATP–pocket axis angle mean/SD, pocket χ₁ mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral PCA entropy) and average across the two replicates.  
   * Assemble all 10 descriptors for the five systems into a single feature table (rows = systems, columns = descriptors).  
   * Perform Ward hierarchical clustering on the feature table, generate a dendrogram and a feature‑heatmap (robust z‑score/IQR scaling).  
   * Plot the global MAFFT MSA and the pocket/high‑consensus MSA panels, all as part of the analysis outputs.

2. **Reporter** – Create a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p24941_ATP/reporter/` that:  
   * Summarizes the literature context for the five kinases/pseudokinases.  
   * Presents the ten‑descriptor table, the dendrogram, the heatmap, and the MSA plots.  
   * Marks a k = 4 cut for interpretation while retaining the full clustering tree.  

All outputs (descriptor table, clustering files, plots, and the HTML report) should be written under the `analysis/` and `reporter/` subdirectories of the working directory, following the standard basenames (no label prefixes). No new simulations, preprocessing, or solvation steps are performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p24941_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
