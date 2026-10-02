# Planner Execution Plan

**Generated:** 2026-09-23 20:23:43
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting Task for q7z7a4_ATP**

1. Using the two 200‑ns production trajectories already present in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7z7a4_ATP/rep01` and `rep02`, run the following per‑replicate analyses: ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
2. Define the ATP‑binding pocket by mapping the residues within 15 Å of ATP in the KAPCA (p17612) reference onto each system via a global MAFFT/MSA; use this consensus pocket for all subsequent calculations.  
3. From each replicate, compute the ten required descriptors (ATP COM distance mean/std, ATP orientation mean/std, pocket χ₁ mean/std, Cα RMSF mean/std, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA entropy) and then average across the two replicates for each system.  
4. Assemble all 37 systems’ descriptor vectors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a feature‑heatmap panel (robust z‑score/IQR scaling) in the `analysis/` directory.  
5. Produce a concise HTML report summarizing the clustering, key literature context, and overall findings, placing it in the `reporter/` directory under the same working path.  

All outputs should use standard basenames (no label prefixes) and respect the case_id `protein_with_ligand` by including the ATP ligand while excluding crystallographic ions. No new preprocessing, simulation setup, or trajectory generation is required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7z7a4_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
