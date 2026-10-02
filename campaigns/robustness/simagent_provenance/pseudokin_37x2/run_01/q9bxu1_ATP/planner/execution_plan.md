# Planner Execution Plan

**Generated:** 2026-09-23 20:59:42
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

1. Run the full set of analyses (ligand pocket distance, consensus_DCCM, consensus_RMSF, consensus_torsions, DCCM, dihedral_PCA, nearby, protein RMSF) on the 200‑ns trajectories of all 37 protein–ATP holo structures located in `/home/akp66103/workspace/.../q9bxu1_ATP`.  
2. For each system, compute the ten required scalar descriptors (ATP COM distance mean/std, ATP axis angle mean/std, pocket χ₁ circular mean/std, consensus‑mapped Cα RMSF mean/std, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA dynamics scalar) and store them in a per‑system analysis folder under `analysis/` using the standard basename (no label prefix).  
3. Assemble all ten descriptors into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust z‑score/IQR‑scaled heatmap.  
4. Produce a concise HTML report in `reporter/` that includes the dendrogram, heatmap, brief literature context, and a k=4 cut for interpretation.  
5. Ensure only the protein and ATP ligand are used (ions excluded) and that no new simulations, preprocessing, or HPC submissions are invoked; analysis is performed solely on the existing trajectories.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9bxu1_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
