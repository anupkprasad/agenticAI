# Planner Execution Plan

**Generated:** 2026-09-23 10:55:14
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis & Reporter Agents**

1. For each of the five protein‑ATP holo systems (p17612:KAPCA, o60674:JAK2, p24941:CDK2, q8ivt5:KSR1, q13418:ILK) in their respective run directories, load the existing 200 ns production trajectories (both replicates).  
2. Using the KAPCA (p17612) pocket definition (residues within 15 Å of ATP), map the consensus pocket onto each protein via a MAFFT star MSA, then compute for each system the ten required scalar descriptors (ATP COM distance mean/std; ATP orientation mean/std; pocket χ₁ circular mean/std; consensus‑mapped Cα RMSF mean/std; N‑lobe↔C‑lobe DCCM mean; shared‑reference dihedral PCA dynamics scalar) by averaging across the two replicates.  
3. Assemble all ten descriptors for all five systems into a single feature table and store it under `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/`.  
4. Perform Ward hierarchical clustering on the feature table, generate a dendrogram and a robust z‑score/IQR‑scaled heatmap, and save these plots in the same analysis directory.  
5. Compile an HTML report—including literature context, the full dendrogram, heatmap, and a concise interpretation (optionally marking a k=4 cut)—in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/reporter/`.  
6. All analyses must use the provided holo trajectories, include the ATP ligand but exclude crystallographic Mg/ions and water; no new preprocessing or simulation steps are to be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/o60674_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
