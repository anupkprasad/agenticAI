# Planner Execution Plan

**Generated:** 2026-09-23 22:29:48
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis & Reporter Agents**

1. For each of the 37 holo‑ATP PDBs in the working directory (case_id = protein_with_ligand), load the pre‑existing 200 ns trajectories and, using only the protein and ATP (exclude crystallographic ions and waters from the source PDB), compute the ten required scalar descriptors: (i) mean and SD of ATP COM distance to the consensus pocket, (ii) mean and SD of ATP orientation versus the pocket axis, (iii) pocket side‑chain χ₁ circular mean and SD, (iv) mean and SD of consensus‑mapped Cα RMSF, (v) mean N‑lobe ↔ C‑lobe DCCM correlation, and (vi) shared‑reference dihedral PCA dynamical scalar.  
2. Assemble all descriptors into a single feature table, apply Ward hierarchical clustering with robust z‑score/IQR scaling, and generate a dendrogram plus a heat‑map panel.  
3. Produce a concise HTML report in the `reporter/` folder that summarizes the literature context, lists the ten descriptors per protein, shows the clustering tree (with a k = 4 cut highlighted) and the heat‑map, and links to the individual analysis output files stored in `analysis/`.  
4. All analyses must use the standard AMBER99SB‑ILDN + TIP3P protocol at 310 K/1 bar with 0.15 M NaCl (no new simulations or preprocessing steps).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
