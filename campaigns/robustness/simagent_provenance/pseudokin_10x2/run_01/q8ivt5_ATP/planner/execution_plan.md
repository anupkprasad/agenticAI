# Planner Execution Plan

**Generated:** 2026-09-22 16:54:13
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporting for the KSR1 holo (q8ivt5_ATP) system**

1. **Data**: Use the two already‑generated 200 ns production trajectories (rep01, rep02) from the q8ivt5_ATP holo structure, which contains protein + ATP and no crystallographic ions.  
2. **Descriptor extraction**: For each replicate compute the ten scalar dynamics descriptors – ATP COM distance (mean & std) to the consensus pocket, ATP orientation (mean & std) relative to the pocket axis, pocket side‑chain χ₁ circular mean & std, consensus‑mapped Cα RMSF (mean & std), N‑lobe ↔ C‑lobe DCCM mean correlation, and the shared‑reference dihedral PCA scalar (√(d_g²+d_c²+pc_rms²)).  
3. **Averaging & plotting**: Average the descriptors over the two replicates, generate time‑series plots (full 200 ns) for each descriptor, and assemble them into a feature table.  
4. **Clustering & visualization**: Apply Ward hierarchical clustering to the ten‑descriptor feature table, produce a dendrogram and a robust z‑score/IQR‑scaled heatmap, and annotate a k = 4 cut for interpretation.  
5. **Report**: Compile an HTML report that presents the methodology, the plots, the clustering figures, and concise literature context for KSR1 holo, ensuring all results are linked to the original trajectory data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q8ivt5_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
