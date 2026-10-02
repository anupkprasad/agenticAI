# Planner Execution Plan

**Generated:** 2026-09-23 23:13:35
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (Analysis → Reporter)**  
1. For each of the 37 human protein‑ATP holo structures (including q13418_ATP), analyze the already‑generated 200 ns trajectories (no new simulations).  
2. Compute the ten required scalar descriptors per system:  
   • ATP COM‑to‑consensus‑pocket distance (mean & SD)  
   • ATP COM‑to‑pocket‑axis angle (mean & SD)  
   • Pocket side‑chain χ₁ circular mean & SD (using residues within 15 Å of ATP, mapped from the KAPCA reference via a global MSA)  
   • Consensus‑mapped Cα RMSF mean & SD  
   • N‑lobe ↔ C‑lobe DCCM mean correlation  
   • Shared‑reference dihedral PCA dynamics scalar (pca_pka_ref_shared_dyn).  
3. Apply the specified analyses—ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF—to each trajectory.  
4. Assemble all ten descriptors into a single feature table, scale (robust z‑score/IQR), run Ward hierarchical clustering, and generate a dendrogram and heatmap (with full tree, k = 4 cut optional).  
5. Write a concise HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP/reporter/` that summarizes the methodology, includes the clustering visualizations, and provides brief literature context.  
6. Store all raw analysis outputs under `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP/analysis/` using the standard basenames (no label prefix).  

**Constraints**  
- Only the protein and ATP ligand are used; crystallographic Mg²⁺/ions are excluded.  
- No preprocessing, simulation setup, or new trajectory generation should be performed.  
- All analyses must be applied uniformly across the 37 systems.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
