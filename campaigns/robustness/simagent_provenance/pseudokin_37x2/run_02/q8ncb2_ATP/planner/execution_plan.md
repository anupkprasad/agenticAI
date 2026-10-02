# Planner Execution Plan

**Generated:** 2026-09-23 23:53:27
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis → Reporter only)**  

1. Use the existing 200‑ns trajectories (two independent replicas per system) for all 37 holo PDBs to perform the following analyses on the full 200 ns: ligand‑pocket COM distance, orientation vs pocket axis, pocket side‑chain χ₁ mean / std, consensus‑mapped Cα RMSF mean / std, N‑/C‑lobe DCCM mean, shared‑reference φ/ψ/χ₁ dihedral PCA entropy, and the additional metrics (consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF).  
2. For each system, average the two replicas to compute the ten scalar descriptors required for clustering (ATP COM distance mean / std, orientation mean / std, χ₁ mean / std, RMSF mean / std, N‑/C‑lobe DCCM mean, PCA entropy).  
3. Assemble the descriptor matrix, perform Ward hierarchical clustering, and generate a dendrogram and heatmap (robust z‑score/IQR scaling) saved in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP/analysis/`.  
4. Produce a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP/reporter/` that includes the clustering results, literature context, and a k = 4 cut‑off interpretation.  

*Pocket mapping*: use the KAPCA (p17612) consensus pocket (residues within 15 Å of ATP) and map it onto the other proteins via global MSA (MAFFT/star) for all analyses.  

*Component handling*: include only the protein and ATP ligand (no crystallographic Mg or ions) as specified by case_id `protein_with_ligand`.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
