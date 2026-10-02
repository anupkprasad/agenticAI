# Planner Execution Plan

**Generated:** 2026-09-22 16:57:22
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis + Reporter Only)**  
1. Analyze the two 200 ns production MD trajectories (rep01, rep02) for each of the ten human protein–ATP holo structures (p17612, o60674, p24941, q8ivt5, q13418, p00533, p23458, q6vab6, q92519, q9y243).  
2. For every system, compute the ten scalar dynamics descriptors: (i) ATP COM distance to the consensus pocket mean & SD, (ii) ATP orientation vs pocket axis mean & SD, (iii) pocket side‑chain χ₁ circular mean & SD, (iv) consensus‑mapped Cα RMSF mean & SD, (v) N‑lobe ↔ C‑lobe DCCM mean correlation, and (vi) shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar vs KAPCA. Use the consensus pocket defined from the KAPCA (p17612) structure, mapped onto each protein via MAFFT star MSA.  
3. Generate plots for each descriptor (full 200 ns trajectories, no truncation), assemble the resulting ten‑column feature table, perform Ward hierarchical clustering, and produce a dendrogram plus robust z‑score/IQR‑scaled heatmap.  
4. Compile an HTML report that includes all plots, the cluster tree (highlighting a k = 4 cut for interpretation), and brief literature context.  
**Constraints**: Use the pre‑existing trajectories; no new simulation, preprocessing, or solvation steps. Include the ATP ligand and any ions added by the simulation protocol, but exclude crystallographic Mg/ions from the source PDB. All analysis must adhere to the default simulation conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/o60674_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
