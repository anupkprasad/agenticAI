# Planner Execution Plan

**Generated:** 2026-09-23 23:15:44
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

1. Using the 200 ns trajectories already generated for the 37 protein‑ATP holo structures, compute the ten required scalar descriptors (ATP‑COM distance mean/SD, ATP orientation mean/SD, pocket χ₁ circular mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, and shared‑reference dihedral‑PCA scalar) for each system and average over the two replicas.  
2. Build a consensus ATP‑binding pocket from KAPCA (p17612) using residues within 15 Å of ATP, map this pocket onto the other proteins via a global MAFFT/star MSA, and generate plots of the overall MSA and the pocket/high‑consensus MSA panels.  
3. Assemble the ten descriptors into a single feature table, perform Ward hierarchical clustering, and output a dendrogram and heatmap (robust z‑score/IQR scaling), marking a k = 4 cut while still including the full tree.  
4. Produce a concise HTML report in the `/reporter/` directory that summarizes the clustering results, includes the MSA plots, and provides brief literature context for the 32 pseudokinases and 5 active kinases.  
5. All analyses must use the protein‑with‑ligand (holo) case: include ATP but exclude all crystallographic Mg/ions from the PDB; trajectories are assumed already solvated with TIP3P, 0.15 M NaCl, 310 K, 1 bar in cubic boxes with 1.2 nm buffer.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
