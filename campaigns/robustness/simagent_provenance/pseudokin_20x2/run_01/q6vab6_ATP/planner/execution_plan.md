# Planner Execution Plan

**Generated:** 2026-09-23 13:22:15
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis and Reporting**

1. Analyze the two existing 200‑ns replicates of the q6vab6 ATP‑bound trajectory (protein+ATP, no crystallographic Mg/ions) to compute the ten scalar dynamics descriptors, then average the values across replicates.  
2. Repeat the same descriptor extraction for all 20 holo kinase systems, using the KAPCA‑defined consensus pocket (15 Å from ATP) mapped by MAFFT, and include all residues within that pocket for χ₁ statistics and consensus‑mapped Cα RMSF.  
3. Generate full‑time‑series plots of the 200‑ns trajectories for each system, and assemble the descriptor table, perform Ward hierarchical clustering (k = 4 cut highlighted), and produce a dendrogram with a z‑score/IQR‑scaled heatmap.  
4. Compile an HTML report that presents the trajectory plots, the feature table, clustering visualizations, and brief literature context for each kinase.  
5. Ensure that only the protein and ATP ligand are retained from the source PDB (ions and water excluded), and that all analyses assume the default AMBER99SB‑ILDN/ TIP3P/310 K/1 bar/0.15 M NaCl conditions.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q6vab6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
