# Planner Execution Plan

**Generated:** 2026-09-23 19:00:30
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

1. Using the 200‑ns, two‑replicate trajectories that already exist for each of the 37 protein–ATP holo structures, run the full set of analyses specified for this study: ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, and protein RMSF.  
2. For every system, compute the ten family‑modular descriptors (ATP COM distance to the consensus pocket, pocket‑axis orientation, consensus Cα RMSF mean/std, pocket χ₁ circular mean, N‑lobe vs C‑lobe DCCM, and shared‑reference dihedral PCA landscape entropy) by averaging over the two replicates.  
3. Assemble these ten scalar descriptors for all 37 systems into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust z‑score/IQR‑scaled feature heatmap.  
4. Create a concise HTML report for each simulation in its dedicated `/reporter/` directory, and a combined report in the top‑level `reporter/` folder that includes literature context, the clustering dendrogram, heatmap, and a brief interpretation (highlight a k = 4 cut but retain the full tree).  
5. All analysis outputs must be stored under the corresponding `/analysis/` subdirectory with standard basenames (no label prefixes). No preprocessing, simulation setup, or HPC submission steps are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p17612_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
