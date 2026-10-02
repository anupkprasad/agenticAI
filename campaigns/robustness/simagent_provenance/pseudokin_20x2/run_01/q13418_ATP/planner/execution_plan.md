# Planner Execution Plan

**Generated:** 2026-09-23 13:17:54
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
1. Load the two 200 ns trajectories from `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q13418_ATP` and confirm that the system contains the protein and ATP ligand only (no crystallographic Mg²⁺, no additional ions or water from the source PDB).  
2. Map the ATP‑binding pocket of KAPCA (p17612) onto q13418 using the global MAFFT/MSA alignment and define pocket residues as those within 15 Å of ATP in the reference.  
3. For each replicate compute the ten scalar dynamics descriptors (mean and SD for ATP COM distance, ATP axis angle, pocket χ₁ mean and SD, Cα RMSF mean and SD, N‑↔C DCCM mean, shared‑reference PCA scalar) and then average the results across the two replicates.  
4. Generate full‑trajectory plots (200 ns) for both replicates and for the averaged data, and assemble an HTML report that includes a table of the ten descriptors, the trajectory visualizations, and a brief literature context.  

**Constraints / Special Requirements**  
- Only protein and ATP ligand are considered; crystallographic ions and water are excluded from the analysis.  
- No new preprocessing, simulation setup, or trajectory generation is performed.  
- The output must contain the full set of ten descriptors (no omissions), the trajectory plots, and a single consolidated HTML report.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q13418_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
