# Planner Execution Plan

**Generated:** 2026-09-23 22:13:36
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis‑only goal for the 37 protein‑ATP holo complexes**

1. Using the existing 200 ns trajectories of the two independent replicas for each system, run the full set of analyses:  
   – ATP COM distance (mean + SD) to the consensus pocket (defined from KAPCA residues within 15 Å);  
   – ATP orientation vs pocket axis (mean + SD angle);  
   – pocket side‑chain χ₁ circular mean + SD;  
   – consensus‑mapped Cα RMSF mean + SD;  
   – N‑lobe ↔ C‑lobe DCCM mean correlation;  
   – shared‑reference φ/ψ/χ₁ dihedral PCA scalar (entropy‑like metric).  
2. Average each descriptor over the two replicas to obtain a single value per system, assemble all 10 descriptors into a feature table, and perform Ward hierarchical clustering (full tree, with a k = 4 cut highlighted).  
3. Generate a dendrogram and a robust z‑score/IQR‑scaled heatmap, and create a concise HTML report that contextualizes the results, placing the clustering tree and heatmap in the report.  
4. Store all analysis outputs under  
   `…/p00533_ATP/analysis/` (standard basenames, no label prefixes) and the final HTML report under  
   `…/p00533_ATP/reporter/`.  
5. Do **not** include any preprocessing, simulation setup, HPC submission, or trajectory generation steps; the analysis and reporter agents are the only required activities.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
