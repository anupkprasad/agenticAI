# Planner Execution Plan

**Generated:** 2026-09-22 18:02:29
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting Goal (for the 10 holo‑protein/ATP systems):**  
1. For each trajectory (200 ns, two independent replicates per protein), compute the following analyses: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, full DCCM, dihedral PCA, nearby residue contacts, and protein RMSF. Use the KAPCA (p17612) ATP‑binding pocket (residues within 15 Å of ATP, mapped to other proteins by a global MAFFT alignment) and include only the protein and ATP ligand, excluding crystallographic Mg/ions and waters.  
2. Store all per‑trajectory output files in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q8ivt5_ATP/analysis/` with standard basenames (no prefix).  
3. Extract the ten scalar descriptors (ATP COM distance mean/std, ATP axis angle mean/std, pocket χ₁ circular mean/std, consensus‑mapped Cα RMSF mean/std, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA dynamics scalar) from both replicates, average across replicates, and assemble a feature table.  
4. Perform Ward hierarchical clustering on the table (robust z‑score/IQR scaling), produce a dendrogram and heat‑map panel (k = 4 cut marked), and compile all results and a concise literature‑context HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q8ivt5_ATP/reporter/`.  
5. All analysis assumes trajectories were generated under AMBER99SB‑ILDN/TIP3P, 310 K, 1 bar, 0.15 M NaCl, cubic box with 1.2 nm buffer; no new simulation or preprocessing steps are performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q8ivt5_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
