# Planner Execution Plan

**Generated:** 2026-09-23 23:00:28
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

1. For each of the 37 holo trajectories (protein + ATP, excluding any crystallographic Mg/ions), compute the ten required scalar descriptors (ATP‑COM distance stats, ATP orientation vs pocket axis, pocket χ₁ mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, and shared‑reference dihedral PCA entropy).  
2. Map the ATP‑binding pocket identified in the KAPCA (p17612) reference (residues within 15 Å of ATP) onto all other proteins using a global MAFFT‑star MSA; generate MSA and pocket‑MSA panels for the report.  
3. Assemble a feature table of these ten descriptors, apply robust z‑score/IQR scaling, perform Ward hierarchical clustering, and output a dendrogram and heat‑map (with k=4 cut highlighted but full tree retained).  
4. Produce a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP/reporter/` that includes the clustering figures, MSA panels, a literature‑context paragraph, and a summary of the ten descriptors for each protein.  
5. All analyses must use only the protein and ligand components; ignore water and any simulation ions (0.15 M NaCl) in the descriptor calculations.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
