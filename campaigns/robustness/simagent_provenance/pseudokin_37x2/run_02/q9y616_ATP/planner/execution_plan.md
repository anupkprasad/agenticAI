# Planner Execution Plan

**Generated:** 2026-09-24 00:44:25
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased goal (analysis + reporter only)**  

Using the already‑generated 200‑ns MD trajectories for the 37 protein‑ATP complexes (two independent replicas per system), perform the following analyses under the “protein_with_ligand” protocol:  

1. Compute the ATP COM distance to the consensus pocket (defined as residues within 15 Å of ATP in KAPCA) and its mean and SD.  
2. Calculate the ATP orientation relative to the pocket axis, reporting mean and SD of the axis angle.  
3. Evaluate pocket side‑chain χ₁ angles, giving circular mean and SD.  
4. Compute RMSF for consensus‑mapped Cα atoms, providing mean and SD.  
5. Generate an N‑lobe↔C‑lobe DCCM and report the mean correlation.  
6. Perform shared‑reference dihedral PCA and calculate the scalar dynamical distance to KAPCA.  

Average each descriptor over the two replicas, assemble a 37 × 10 feature matrix, run Ward hierarchical clustering (full dendrogram and heatmap with robust z‑score/IQR scaling), and produce an HTML report summarizing the clustering and key literature context.  

Store all analysis outputs in the `analysis/` subdirectory and the final report in the `reporter/` subdirectory of the working directory. No new preprocessing or simulation steps are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
