# Planner Execution Plan

**Generated:** 2026-09-23 19:53:25
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
Analyze the 37 existing 200 ns trajectories (two replicates each) for the protein–ATP holo complexes, focusing on protein and ATP atoms only. Pocket residues are defined by the KAPCA consensus (within 15 Å of ATP) and mapped onto each protein via MAFFT alignment. For each system compute ligand‑pocket distances, consensus DCCM/RMSF/torsions, dihedral PCA, nearby, and protein RMSF, averaging over the two replicates, and output per‑system files in **/analysis/** with standard basenames. Assemble a single table of the ten required scalar descriptors (ATP COM distance mean/std; pocket axis mean/std; pocket χ₁ mean/std; consensus Cα RMSF mean/std; N‑lobe vs C‑lobe DCCM mean; dihedral PCA landscape entropy) for all 37 proteins. In the reporter step, run Ward hierarchical clustering on the descriptor table, generate a dendrogram plus a robust‑scaled feature heat‑map, and compile a concise HTML report (with literature context and a k=4 cut highlight) under **/reporter/**. All analyses use the existing trajectories and respect the default simulation conditions.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q6vab6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
