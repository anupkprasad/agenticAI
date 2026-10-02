# Planner Execution Plan

**Generated:** 2026-09-23 19:03:08
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis → Reporter Workflow**

1. Run the full set of analyses (ligand pocket distance, consensus_DCCM, consensus_RMSF, consensus_torsions, DCCM, dihedral_PCA, nearby, protein RMSF) on each of the 37 existing 200‑ns MD trajectories (two 200‑ns replicates per system).  
2. For each system, extract the ten required scalar descriptors (ATP‑COM distance mean & SD, ATP‑pocket axis angle mean & SD, pocket χ₁ circular mean & SD, consensus Cα RMSF mean & SD, N‑/C‑lobe DCCM mean, and shared‑reference dihedral‑PCA entropy) by averaging over the two replicates.  
3. Compile all descriptors into a single feature table, apply robust z‑score/IQR scaling, perform Ward hierarchical clustering, and generate a dendrogram with a heat‑map of the scaled features.  
4. Store all per‑system analysis outputs (plain‑text or CSV) in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p24941_ATP/analysis/` using standard basenames (no prefix).  
5. Produce a concise HTML report, including a literature context paragraph, the dendrogram, heat‑map, and the feature table, and save it under  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p24941_ATP/reporter/`.  
6. All analyses must use the protein–ATP holo structure (protein + ligand, no crystallographic ions or waters) as specified by the `case_id: protein_with_ligand`.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p24941_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
