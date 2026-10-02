# Planner Execution Plan

**Generated:** 2026-09-23 20:52:17
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the existing 200 ns production trajectories for q96qs6_ATP (no new simulation or preprocessing).  
Compute the full set of per‑trajectory metrics: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby, and protein RMSF.  
From the two replicates derive the ten required scalar dynamics descriptors (ATP COM distance mean / SD to the consensus pocket, ATP orientation mean / SD vs pocket axis, pocket side‑chain χ₁ circular mean / SD, consensus‑mapped Cα RMSF mean / SD, N‑lobe ↔ C‑lobe DCCM mean correlation, and shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar) and write each value to /analysis/ using standard basenames (no label prefixes).  
Store all results under the analysis directory and generate a concise HTML report in /reporter/ that presents the descriptors, key plots, and brief literature context, ensuring the protein_with_ligand case (ATP included, ions and water excluded) is honored.  
No additional preprocessing, solvation, or new trajectory generation is performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q96qs6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
