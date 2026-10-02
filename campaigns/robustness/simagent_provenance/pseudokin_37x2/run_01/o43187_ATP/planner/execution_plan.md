# Planner Execution Plan

**Generated:** 2026-09-23 18:46:32
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis and Reporter Task**  
1. For each of the 37 pre‑simulated protein–ATP holo systems (two 200 ns replicates each), run the full set of analyses: ligand‑pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, and protein RMSF.  
2. Define the consensus ATP‑binding pocket from KAPCA (residues within 15 Å of ATP), map it onto the other proteins via a global MAFFT alignment, and use this mapping to extract the ten scalar descriptors per system (ATP COM distance mean/std, ATP orientation mean/std, pocket χ₁ mean/std, Cα RMSF mean/std, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral PCA entropy).  
3. Average the descriptor values across the two replicates for each system, assemble them into a single feature table, and perform Ward hierarchical clustering (robust z‑score/IQR scaling). Generate a dendrogram and a feature‑heatmap panel, marking a k = 4 cut for interpretation.  
4. For each system, write the analysis outputs (standard basenames, no label prefixes) under  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o43187_ATP/analysis/`  
   and create a concise HTML report under  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o43187_ATP/reporter/`.  
5. Produce a combined HTML report summarizing the dendrogram, heatmap, descriptor table, and brief literature context for the entire set of 37 holo structures.  
All analysis must respect the case_id **protein_with_ligand** (protein + ATP only, no crystallographic ions), and use the default physiological simulation conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl, cubic box with 1.2 nm buffer). No additional preprocessing, simulation setup, or HPC steps are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o43187_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
