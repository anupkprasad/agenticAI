# Planner Execution Plan

**Generated:** 2026-09-23 15:19:27
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis and Reporter Agents**

1. For each of the 20 protein–ATP holo complexes, analyze the two existing 200‑ns trajectories (full length, no truncation) to compute the ten required scalar dynamics descriptors:  
   1. ATP COM distance to the consensus pocket – mean  
   2. ATP COM distance to the consensus pocket – standard deviation  
   3. ATP orientation vs pocket axis – mean angle  
   4. ATP orientation vs pocket axis – standard deviation of angle  
   5. Pocket side‑chain χ₁ circular mean  
   6. Pocket side‑chain χ₁ circular standard deviation  
   7. Consensus‑mapped Cα RMSF – mean  
   8. Consensus‑mapped Cα RMSF – standard deviation  
   9. N‑lobe ↔ C‑lobe DCCM mean correlation  
   10. Shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar (pca_pka_ref_shared_dyn)

   Average each descriptor across the two replicates.

2. Assemble a 20 × 10 feature table from these averaged values.

3. Apply Ward hierarchical clustering to the feature table, generate a dendrogram and a feature‑heatmap panel (using robust z‑score/IQR scaling), and mark a k = 4 cut for interpretation while still outputting the full tree.

4. Produce a single HTML report that presents the dendrogram, heat‑map, and a concise literature context for each protein, placing all outputs under  
   `…/q13418_ATP/reporter/` and the feature table under `…/q13418_ATP/analysis/`.

**Focus and Constraints**

- Analyses are limited to the protein and ATP ligand; crystallographic Mg/ions and any other components are excluded, consistent with the `protein_with_ligand` case_id.  
- All trajectories were generated under the standard physiological conditions (AMBER99SB‑ILDN, TIP3P, 310 K, 1 bar, 0.15 M NaCl); no changes to these conditions are required for the analysis stage.  
- No preprocessing, simulation setup, or new simulation runs are to be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q13418_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
