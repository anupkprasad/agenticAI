# Planner Execution Plan

**Generated:** 2026-09-22 18:23:07
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

1. **Analyze the existing 200 ns production trajectories** for each of the ten protein‑ATP holo complexes (UniProt IDs: p17612, o60674, p24941, q8ivt5, q13418, p00533, p23458, q6vab6, q92519, q9y243) under the default physiological conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl).  
2. **Compute the specified metrics** for every trajectory: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF; map the ATP‑binding pocket defined in KAPCA (p17612) onto the other proteins using a global MSA.  
3. **Extract the ten scalar descriptors** (ATP‑COM distance statistics, pocket axis orientation statistics, pocket χ₁ circular mean / sd, consensus‑mapped Cα RMSF mean / sd, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral PCA scalar) by averaging over the two replicates for each system.  
4. **Assemble a feature table, apply Ward hierarchical clustering, and generate** a dendrogram and robustly scaled heat‑map (z‑score/IQR) summarizing the ten descriptors; keep the full tree but mark a k = 4 cut for interpretation.  
5. **Write outputs to** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p00533_ATP/analysis/` (raw metrics, feature table, plots) and produce a concise HTML report with literature context in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p00533_ATP/reporter/`.  
6. **Only the protein and ATP ligand are considered** (case_id = protein_with_ligand); exclude crystallographic Mg/ions and any other ions not required by the simulation directive.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p00533_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
