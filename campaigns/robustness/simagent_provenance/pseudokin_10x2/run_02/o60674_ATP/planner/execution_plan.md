# Planner Execution Plan

**Generated:** 2026-09-22 18:04:47
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis and Reporter Agents**

1. For each of the 10 protein‑ATP holo complexes (p17612 KAPCA, o60674 JAK2, p24941 CDK2, q8ivt5 KSR1, q13418 ILK, p00533 EGFR, p23458 JAK1, q6vab6 KSR2, q92519 TRIB2, q9y243 AKT3), process the two 200 ns production trajectories (full 200 ns, no truncation). Compute the ten required scalar descriptors—ATP COM distance to the consensus pocket (mean ± SD), ATP orientation vs pocket axis (mean ± SD), pocket side‑chain χ₁ circular mean ± SD, consensus‑mapped Cα RMSF mean ± SD, N‑lobe ↔ C‑lobe DCCM mean correlation, and shared‑reference dihedral PCA landscape entropy (pca_pka_ref_shared_dyn)—as well as the additional per‑system analyses (ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF). Use the KAPCA (p17612) 15 Å pocket definition, mapped onto each system via MAFFT star MSA, and include only the protein, ligand, and required ions (case_id = protein_with_ligand).  
2. Aggregate all descriptors into a single feature table, apply robust z‑score/IQR scaling, perform Ward hierarchical clustering, and generate a dendrogram plus feature‑heatmap panel.  
3. Produce a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/o60674_ATP/reporter/` that summarizes the analyses, displays the dendrogram and heatmap, includes a k = 4 cut for interpretation, and provides brief literature context. All intermediate analysis files should be written under the same directory’s `analysis/` folder with standard basenames (no label prefix). No preprocessing, simulation, or HPC steps are required or referenced.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/o60674_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
