# Planner Execution Plan

**Generated:** 2026-09-23 20:10:38
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis & Reporter**

1. **Analysis** – For the already‑run 200 ns trajectories of each holo system (including ATP and excluding crystallographic Mg/ions), compute the following per‑replicate metrics:  
   • ATP‑COM to consensus pocket distance (mean & SD)  
   • ATP‑pocket axis orientation (mean & SD)  
   • Pocket side‑chain χ₁ circular mean & SD  
   • Consensus‑mapped Cα RMSF (mean & SD)  
   • N‑lobe ↔ C‑lobe DCCM mean correlation  
   • Shared‑reference φ/ψ/χ₁ dihedral PCA entropy (√(d_g² + d_c² + pc_rms²))  
   Then average across the two replicates for each system. Store all results in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7rtn6_ATP/analysis/` using standard basenames (no label prefixes).

2. **Reporter** – Assemble the ten scalar descriptors for all 37 systems into a single feature table, perform Ward hierarchical clustering (k‑cut of 4 optional for interpretation), and generate a combined HTML report in  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7rtn6_ATP/reporter/`.  
   The report must include a dendrogram, a robust z‑score/IQR‑scaled heatmap, and brief literature context.  

All analyses must use the default physiological conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl, cubic box with 1.2 nm buffer). No preprocessing, simulation setup, or new trajectory generation is required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7rtn6_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
