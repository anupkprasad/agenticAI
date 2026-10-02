# Planner Execution Plan

**Generated:** 2026-09-23 15:07:06
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

1. Using the existing 200‑ns MD trajectories (two independent replicates per system), compute the ten required scalar dynamics descriptors for every protein–ATP holo structure, averaging across replicates where specified.  
2. The descriptors to calculate are:  
   - ATP COM distance to the consensus pocket (mean and SD)  
   - ATP orientation vs. pocket axis (mean and SD)  
   - Pocket side‑chain χ₁ circular mean and SD  
   - Flexibility of consensus‑mapped Cα atoms (mean RMSF and SD)  
   - N‑lobe ↔ C‑lobe DCCM mean correlation  
   - Shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar relative to KAPCA.  
   Pocket residues are defined by the 15 Å proximity to ATP in the KAPCA (p17612) reference structure and mapped onto all other proteins via a global MAFFT MSA.  
3. Assemble these descriptors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram and a feature‑heatmap panel (robust z‑score/IQR scaling).  
4. Produce a consolidated HTML report containing the dendrogram, heatmap, and concise literature context for each protein, marking a k = 4 cut for interpretation but retaining the full tree.  
5. No new preprocessing, simulation setup, or trajectory generation is required; only analysis and reporting stages will be executed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/o60674_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
