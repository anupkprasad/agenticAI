# Planner Execution Plan

**Generated:** 2026-09-23 14:07:07
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal for the Analysis → Reporter Pipeline**

1. **Analyze the existing 20 holo kinase trajectories** (each with two 200 ns replicates) that already contain protein, ATP ligand, solvent, and ions; exclude any crystallographic ions from the original PDB.  
2. **Compute, for every system, the ten scalar dynamics descriptors**: ATP COM distance mean & SD to the consensus pocket; ATP axis angle mean & SD; pocket side‑chain χ₁ circular mean & SD; consensus‑mapped Cα RMSF mean & SD; N‑lobe ↔ C‑lobe DCCM mean; shared‑reference PCA scalar; then average each descriptor over the two replicates.  
3. **Map the ATP‑binding pocket using the KAPCA (p17612) reference** via a global sequence alignment (MAFFT/star MSA) and apply the mapping to all other proteins.  
4. **Generate full‑length (200 ns) trajectory plots** for each system and assemble a single feature table of the ten descriptors.  
5. **Run Ward hierarchical clustering** on the standardized feature table (robust z‑score/IQR scaling), produce a dendrogram and a feature‑heatmap panel, and include a k = 4 cut for interpretation.  
6. **Compile an HTML report** that presents the plots, clustering results, heatmap, dendrogram, and a brief literature context for each protein. No new simulations, preprocessing, or HPC submissions are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p51841_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
