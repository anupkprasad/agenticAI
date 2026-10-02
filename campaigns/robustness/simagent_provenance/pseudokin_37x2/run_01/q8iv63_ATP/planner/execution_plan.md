# Planner Execution Plan

**Generated:** 2026-09-23 20:05:52
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal for the Analysis → Reporter Workflow**

1. For each of the 37 protein‑ATP holo trajectories (two 200 ns replicates each), compute the ten required scalar dynamics descriptors, using the ATP ligand and the consensus pocket defined by mapping KAPCA residues (15 Å cutoff) onto every protein via a global MAFFT alignment; average the values across the two replicates.  
2. Additionally, calculate per‑trajectory ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, global DCCM, dihedral PCA, nearby residue contacts, and protein RMSF, saving all results under the system’s `/analysis/` folder with standard basenames (no label prefix).  
3. Assemble the descriptor table for all systems, perform Ward hierarchical clustering (with robust z‑score/IQR scaling), and output a single dendrogram plus a feature‑heatmap panel.  
4. Generate a concise HTML report for each system (and an aggregated report) in the `/reporter/` folder, including the dendrogram, heatmap, scalar descriptor summaries, and brief literature context.  
5. All analyses must exclude crystallographic Mg/ions, include only the ATP ligand, and use the default AMBER99SB‑ILDN/TIP3P/310 K/1 bar/0.15 M NaCl cubic box conditions as already satisfied in the existing trajectories.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8iv63_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
