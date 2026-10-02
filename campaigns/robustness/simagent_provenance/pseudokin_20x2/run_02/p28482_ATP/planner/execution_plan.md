# Planner Execution Plan

**Generated:** 2026-09-23 16:01:12
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Perform full‑trajectory analysis of the 20 existing 200‑ns protein–ATP holo MD replicates (two 200‑ns trajectories per system) located in the working directory.  
For each system compute the ten scalar dynamics descriptors: ATP COM distance mean and standard deviation to the consensus pocket, ATP orientation mean and standard deviation relative to the pocket axis, pocket side‑chain χ₁ mean and standard deviation, consensus‑mapped Cα RMSF mean and standard deviation, N‑lobe ↔ C‑lobe DCCM mean correlation, and the shared‑reference dihedral PCA dynamics scalar, using the ATP‑binding pocket defined from the KAPCA reference and mapped via a global MSA.  
Assemble the descriptors into a single feature table, apply Ward hierarchical clustering, and generate a dendrogram plus a robust z‑score/IQR‑scaled feature‑heatmap panel.  
Produce a consolidated HTML report (with brief literature context) in the reporter directory, with all analysis outputs stored under the analysis subdirectory.  
Constraints: follow case_id *protein_with_ligand* (include only protein and ATP ligand, exclude crystallographic ions), analyze the full 200‑ns windows, and do not perform any new preprocessing, simulation, or HPC submission steps.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p28482_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
