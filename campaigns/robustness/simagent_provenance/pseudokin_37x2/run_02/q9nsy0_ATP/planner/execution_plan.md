# Planner Execution Plan

**Generated:** 2026-09-24 00:26:42
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis & Reporter only)**  
1. Use the existing 2×200‑ns GROMACS trajectories for each of the 37 human protein–ATP holo structures in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP`.  
2. For every system, compute the ten required scalar descriptors:  
   - ATP COM distance to the consensus pocket (mean & std)  
   - ATP orientation vs. pocket axis (mean & std)  
   - Pocket side‑chain χ₁ circular mean & std  
   - Consensus‑mapped Cα RMSF mean & std  
   - N‑lobe ↔ C‑lobe DCCM mean correlation  
   - Shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar  
   Use the ATP ligand present in the trajectories; exclude crystallographic ions and water as per the original preprocessing.  
3. Assemble the 10‑descriptor feature table, perform Ward hierarchical clustering, and generate a robust z‑score/IQR‑scaled dendrogram and heatmap, saving all plots and the table in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP/analysis/`.  
4. Produce a concise HTML report (with brief literature context and the clustering visualizations) and place it in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP/reporter/`.  
5. All analysis assumes the trajectories were generated with amber99sb-ildn/TIP3P at 310 K, 1 bar, 0.15 M NaCl in a cubic box (1.2 nm buffer).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
