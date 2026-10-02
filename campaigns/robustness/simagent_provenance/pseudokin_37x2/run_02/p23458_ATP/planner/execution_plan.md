# Planner Execution Plan

**Generated:** 2026-09-23 22:32:19
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the two 200‑ns trajectories for each of the 37 holo protein–ATP systems in /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP. For every system compute the ten scalar descriptors—mean / SD of ATP COM distance to the consensus pocket (defined by KAPCA residues within 15 Å of ATP and mapped to each target via MSA), mean / SD of ATP orientation relative to the pocket axis, circular mean / SD of pocket side‑chain χ₁ angles, mean / SD of RMSF of consensus‑mapped Cα atoms, mean N‑lobe ↔ C‑lobe DCCM correlation, and the shared‑reference dihedral‑PCA entropy; average the values over the two replicas. Compile these averages into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram and a robust‑scaled heatmap (robust z‑score/IQR) in /home/.../p23458_ATP/analysis/ using standard basenames (no label prefix). Finally, create a concise HTML report in /home/.../p23458_ATP/reporter/ that presents the dendrogram, heatmap, marks a k = 4 cut for interpretation, and includes brief literature context. All analyses should use the existing trajectories under the default AMBER99SB‑ILDN/TIP3P/310 K/1 bar/0.15 M NaCl conditions already applied.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
