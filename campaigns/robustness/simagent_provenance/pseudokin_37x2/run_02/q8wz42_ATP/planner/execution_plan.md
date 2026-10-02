# Planner Execution Plan

**Generated:** 2026-09-24 00:08:39
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis and Reporting Tasks (for all 37 holo systems):**  
1. Load the existing 200‑ns production trajectories (two 200‑ns replicas per system) and compute the ten required scalar descriptors for each system: (i) ATP COM distance to the consensus pocket (mean and SD), (ii) ATP orientation vs pocket axis (mean and SD of axis angle), (iii) pocket side‑chain χ₁ circular mean and SD, (iv) consensus‑mapped Cα RMSF mean and SD, (v) N‑lobe ↔ C‑lobe DCCM mean correlation, and (vi) shared‑reference φ/ψ/χ₁ dihedral PCA scalar.  
2. Map the ATP‑binding pocket from KAPCA (p17612) onto each protein using a global MAFFT alignment, then define the pocket residues within 15 Å of ATP for all analyses.  
3. Average the descriptors over the two replicas, assemble them into a feature table, and perform Ward hierarchical clustering. Produce a dendrogram and a heat‑map of the scaled (robust z‑score/IQR) features.  
4. Generate an HTML report (under `/…/q8wz42_ATP/reporter/`) that includes the dendrogram, heat‑map, concise literature context, and marks a k = 4 cut for interpretation while also presenting the full tree.  

**Constraints:**  
- Only protein and ATP ligand are included; all crystallographic ions and waters are excluded per `case_id: protein_with_ligand`.  
- Analysis is performed on the full 200‑ns trajectory for each replica; no truncation.  
- All outputs must reside in `/…/q8wz42_ATP/analysis/` (feature table, clustering files) and the report directory as specified.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
