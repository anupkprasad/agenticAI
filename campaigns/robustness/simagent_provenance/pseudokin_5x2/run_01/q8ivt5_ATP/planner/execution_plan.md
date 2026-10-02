# Planner Execution Plan

**Generated:** 2026-09-23 10:52:51
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis → Reporter**

1. **Analysis**:  
   For each of the five holo trajectories (p17612, o60674, p24941, q8ivt5, q13418) run a full‑length (200 ns) analysis.  
   - Define the ATP‑binding pocket using the KAPCA (p17612) reference (15 Å from ATP), map the pocket onto all proteins with a global MAFFT MSA, and record pocket residues.  
   - Compute the ten scalar descriptors per system (ATP COM distance mean/std, ATP orientation mean/std, pocket χ₁ circular mean/std, mean/std RMSF of consensus‑mapped Cα atoms, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral PCA dynamics scalar).  
   - Store all descriptor values in `/home/akp66103/.../analysis/` with standard basenames (no prefixes).  

2. **Reporter**:  
   - Assemble the descriptor matrix, perform Ward hierarchical clustering, and generate a dendrogram and heatmap (robust z‑score/IQR scaling).  
   - Create a single HTML report in `/home/akp66103/.../reporter/` that includes the dendrogram, heatmap, and a concise literature context, marking a k=4 cut for interpretation but retaining the full tree.

All outputs should preserve the user’s requirement that no simulation steps, preprocessing, or HPC submissions be performed; only the existing trajectories are analyzed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/q8ivt5_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
