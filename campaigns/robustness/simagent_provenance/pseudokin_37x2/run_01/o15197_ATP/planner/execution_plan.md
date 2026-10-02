# Planner Execution Plan

**Generated:** 2026-09-23 18:43:23
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Re‑phrased Goal for the Analysis & Reporter Agents**

1. **Analysis** – For each of the 37 human protein‑ATP holo structures (PDBs already in `/home/akp66103/workspace/.../run_01/o15197_ATP/`), use the existing 200‑ns production trajectories (both replicates) to run the following per‑system analyses: ligand‑pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby residues, and protein RMSF. From these, compute the ten required scalar descriptors (ATP COM distance mean & SD, ATP‑pocket axis angle mean & SD, pocket χ₁ circular mean & SD, consensus‑mapped Cα RMSF mean & SD, N‑lobe ↔ C‑lobe DCCM mean, dihedral PCA landscape entropy). Store all per‑system outputs in `…/o15197_ATP/analysis/` using standard basenames without labels.  
2. **Aggregation & Clustering** – Compile the ten descriptors for all 37 systems into a single feature table, apply Ward hierarchical clustering, and generate a dendrogram plus a feature‑heatmap panel (robust z‑score/IQR scaling).  
3. **Reporter** – Create a concise HTML report for each system in `…/o15197_ATP/reporter/` summarizing the analyses, and a combined report in the same directory that includes the dendrogram, heatmap, and brief literature context.  
4. **Constraints** – Do **not** truncate trajectories; use the full 200‑ns window. Include ATP as the ligand and exclude any crystallographic Mg/ions (case_id = protein_with_ligand). No new preprocessing or simulation steps are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o15197_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
