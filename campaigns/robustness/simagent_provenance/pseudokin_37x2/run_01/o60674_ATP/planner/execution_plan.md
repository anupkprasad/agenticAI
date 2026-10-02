# Planner Execution Plan

**Generated:** 2026-09-23 18:45:34
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Analysis & Reporter Scope for the 37 protein–ATP holo systems (no new preprocessing or simulation):**  
1. Load the pre‑existing 200‑ns trajectories for each of the 37 holo structures (protein + ATP, no crystallographic ions) and perform the following per‑trajectory analyses: ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.  
2. For every system compute the ten family‑modular descriptors: ATP COM distance (mean & SD) to the consensus pocket, ATP orientation vs pocket axis (mean & SD), pocket side‑chain χ₁ circular mean & SD, consensus‑mapped Cα RMSF (mean & SD), N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral PCA dynamics scalar.  
3. Aggregate the descriptor matrix across all 37 systems, apply Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a dendrogram plus heat‑map panel.  
4. Produce a concise HTML report for each system in …/o60674_ATP/reporter/ and a combined campaign report including literature context, clustering interpretation (including a k=4 cut), and all visual panels.  
5. All analyses must respect the user’s component selection (protein + ligand only, ions excluded) and default simulation conditions (amber99sb-ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl, cubic box). No new preprocessing, solvation, or trajectory generation may be performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o60674_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
