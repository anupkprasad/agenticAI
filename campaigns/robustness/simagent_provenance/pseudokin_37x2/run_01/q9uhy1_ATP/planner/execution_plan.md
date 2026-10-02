# Planner Execution Plan

**Generated:** 2026-09-23 21:08:49
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

1. **Analysis**  
   - For each of the 37 protein–ATP holo trajectories (two 200 ns replicas per system, available in *rep01*/*rep02*), compute the ten required scalar dynamics descriptors (ATP‑COM distance statistics, ATP‑pocket axis angles, pocket χ₁ circular mean/SD, consensus‑mapped Cα RMSF mean/SD, N‑lobe↔C‑lobe DCCM mean, and shared‑reference dihedral‑PCA entropy).  
   - Output one descriptor CSV per system in `/…/q9uhy1_ATP/analysis/` using the base filename `<UniProtID>_descriptors.csv` (no prefix).  
   - Aggregate all 37 descriptor tables into a single feature matrix, perform Ward hierarchical clustering, and generate a dendrogram + z‑score/IQR‑scaled heatmap.  
   - Save the feature matrix and clustering visualizations in the same *analysis* directory.

2. **Reporter**  
   - Using the clustering results, create a concise HTML report in `/…/q9uhy1_ATP/reporter/` that summarizes: (i) descriptor distributions per system, (ii) the dendrogram with a k = 4 cut highlighted, (iii) the heatmap, and (iv) brief literature context for pseudokinase vs active kinase groups.  
   - Include links to the raw descriptor CSVs and the generated plots.

**Constraints & Focus**  
- Only the protein and ATP ligand components are considered; crystallographic Mg²⁺/ions are excluded from all analyses.  
- No preprocessing, simulation setup, or trajectory generation steps are performed—use the existing 200 ns trajectories.  
- All analyses and outputs must adhere to the default physiological conditions specified (amber99sb-ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9uhy1_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
