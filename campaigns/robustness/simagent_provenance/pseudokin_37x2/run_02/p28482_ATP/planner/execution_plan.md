# Planner Execution Plan

**Generated:** 2026-09-23 22:47:52
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

1. **Analysis** – For each of the 37 human protein–ATP holo trajectories (already generated), compute the ten required scalar descriptors per system (ATP COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ circular mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA scalar) by averaging over the two 200 ns replicas. The ATP pocket is defined by residues within 15 Å of ATP in the KAPCA (p17612) structure; map these residues onto each protein via a global MAFFT MSA. Use only the protein, ligand, and 0.15 M NaCl, with TIP3P water, 310 K, 1 bar, cubic box, 1.2 nm buffer, as per the directive.  
2. **Reporter** – Assemble the ten‑descriptor feature table for all systems, perform Ward hierarchical clustering, and generate a dendrogram and heat‑map (robust z‑score/IQR scaling). Produce a single HTML report summarizing the literature context, the full clustering tree (with optional k=4 cut), and the descriptor table. All outputs should be written under the analysis and reporter directories of the given working directory.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
