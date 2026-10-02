# Planner Execution Plan

**Generated:** 2026-09-23 20:56:33
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis → reporter only)**  

1. **Analysis**: Load the existing 200 ns trajectories for *q9nsy0_ATP* (found in the run directory). Compute the following descriptors and save each with a standard basename in the `/analysis/` subfolder:  
   - Ligand pocket distance (ATP COM ↔ consensus pocket) – mean and std.  
   - Consensus DCCM (correlation matrix of consensus‑mapped residues).  
   - Consensus RMSF (per‑residue and overall mean/std for consensus Cα atoms).  
   - Consensus torsions (χ₁ angles for pocket side chains).  
   - Full protein DCCM.  
   - Dihedral PCA projections and landscape entropy.  
   - Nearby‑residue distance matrix.  
   - Protein RMSF for all residues.  
   Additionally, generate a CSV file containing the ten family‑modular scalar descriptors required for clustering (ATP COM distance mean/std, pocket‑axis orientation mean/std, consensus‑Cα RMSF mean/std, pocket χ₁ circular mean/std, N‑lobe ↔ C‑lobe DCCM mean, dihedral‑PCA landscape entropy).  

2. **Reporter**: Using the analysis outputs, compile a concise HTML report in `/reporter/` that summarizes the key metrics, includes brief literature context, and presents the computed descriptor values in a readable format. No new simulations, preprocessing, or HPC submissions are performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9nsy0_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
