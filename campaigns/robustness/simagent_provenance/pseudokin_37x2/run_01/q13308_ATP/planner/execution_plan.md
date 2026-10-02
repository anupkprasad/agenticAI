# Planner Execution Plan

**Generated:** 2026-09-23 19:38:08
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis → Reporter Workflow**

1. **Analysis Tasks**  
   - For each of the 37 protein–ATP holo trajectories, compute:  
     - Ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
     - Family‑modular descriptors using the KAPCA (p17612) reference pocket: ATP COM distance to the consensus pocket (mean & std), pocket‑axis orientation (mean & std), consensus Cα RMSF mean & std, pocket χ₁ circular mean & std, N‑lobe ↔ C‑lobe DCCM mean, and dihedral PCA landscape entropy.  
   - Average all metrics across the two 200 ns replicates per system.  
   - Compile the ten descriptors into a single feature table for all 37 systems.

2. **Clustering & Reporting**  
   - Perform Ward hierarchical clustering on the feature table, generating a dendrogram and a feature‑heatmap (robust z‑score / IQR scaling).  
   - Produce a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13308_ATP/reporter/` that includes the dendrogram, heatmap, and brief literature context, marking a k = 4 cut for interpretation while presenting the full tree.

**Outputs**  
- Analysis files (CSV/JSON) in `/analysis/` under the working directory for each system.  
- Single HTML report in `/reporter/` with dendrogram, heatmap, and discussion.  

**Constraints**  
- Use only the existing trajectories (no new simulation, preprocessing, or solvation steps).  
- Apply the same default physiological conditions used in the simulation (amber99sb-ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl) for consistency when interpreting descriptors.  
- Maintain all requested metrics; do not drop any descriptor.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13308_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
