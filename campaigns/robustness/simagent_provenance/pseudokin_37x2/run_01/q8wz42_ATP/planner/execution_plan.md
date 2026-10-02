# Planner Execution Plan

**Generated:** 2026-09-23 20:40:44
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis & Reporter Agents**

1. **Analysis**  
   • For each of the 37 protein‑ATP holo systems, load the two existing 200 ns trajectory replicas and perform the following analyses: ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
   • Compute the 10 required scalar descriptors (ATP COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ circular mean/SD, consensus‑Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, dihedral PCA‑landscape entropy) for each system by averaging across the two replicates.  
   • Aggregate all descriptors into a single feature table, perform Ward hierarchical clustering, and generate a full dendrogram and feature‑heatmap (robust z‑score/IQR scaling) with a k = 4 cut highlighted.  
   • Output all analysis files (e.g., .csv, .png, .pdf) to `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8wz42_ATP/analysis/` using standard basenames (no label prefix).

2. **Reporter**  
   • Compile the analysis results into a concise HTML report placed in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8wz42_ATP/reporter/`.  
   • Include literature context, the dendrogram/heatmap panel, and a brief interpretation of the k = 4 clustering.  
   • Ensure the report references the ATP‑binding pocket defined from KAPCA (p17612) and its mapping onto the other proteins via global and pocket‑specific MSAs.  

**Constraints**  
- Do **not** perform any preprocessing, simulation setup, HPC submission, equilibration, production runs, or solvation steps; use the existing trajectory files.  
- All analyses assume the default AMBER99SB‑ILDN/Tip3p/310 K/1 bar/0.15 M NaCl conditions already applied during the earlier simulation phase.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8wz42_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
