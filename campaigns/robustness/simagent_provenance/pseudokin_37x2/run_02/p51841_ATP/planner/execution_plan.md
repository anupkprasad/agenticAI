# Planner Execution Plan

**Generated:** 2026-09-23 22:48:55
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis & reporter only)**  
For each of the 37 pre‑simulated protein–ATP holo trajectories (stored in the current working directory), perform the following analyses on the full 200 ns of each replica:  
1. Compute the ATP COM distance to the consensus pocket and its standard deviation;  
2. Determine the ATP orientation relative to the pocket axis and its mean and standard deviation;  
3. Calculate the pocket side‑chain χ₁ circular mean and standard deviation;  
4. Measure RMSF of the consensus‑mapped Cα atoms (mean and standard deviation);  
5. Evaluate the mean correlation in the N‑lobe ↔ C‑lobe DCCM;  
6. Compute the shared‑reference dihedral PCA entropy (pca_pka_ref_shared_dyn).  
Additionally, run the supplementary analyses requested (ligand‑pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF) for each system.  
Compile all ten scalar descriptors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram and IQR‑scaled heatmap.  
Finally, produce a concise HTML report summarizing the results, literature context, and a k = 4 cut for interpretation, placing all outputs under the analysis and reporter subdirectories of the working directory.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
