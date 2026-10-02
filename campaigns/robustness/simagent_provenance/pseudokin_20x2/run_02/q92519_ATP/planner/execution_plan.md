# Planner Execution Plan

**Generated:** 2026-09-23 15:32:53
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

1. For each of the 20 human protein–ATP holo complexes, analyze the two existing 200 ns MD trajectories in full (no truncation).  
2. Compute the ten required scalar descriptors per system: (i) ATP COM‑pocket distance mean and SD, (ii) ATP orientation‑pocket axis mean and SD, (iii) pocket side‑chain χ₁ circular mean and SD, (iv) consensus‑mapped Cα RMSF mean and SD, (v) N‑lobe ↔ C‑lobe DCCM mean correlation, and (vi) shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar relative to KAPCA.  
3. Assemble all descriptors into a single feature table, apply Ward hierarchical clustering, and generate a dendrogram and robust (z‑score/IQR) feature‑heatmap panel.  
4. Produce a combined HTML report that includes the clustering visualization and brief literature context, placing the analysis results under  
   `…/q92519_ATP/analysis/` and the report under `…/q92519_ATP/reporter/`.  
5. All analyses must use the AMBER99SB‑ILDN force field, TIP3P water, 310 K, 1 bar, 0.15 M NaCl, and the ATP‑binding pocket defined by residues within 15 Å of ATP in the KAPCA reference; map this pocket onto each protein via a global MAFFT MSA.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q92519_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
