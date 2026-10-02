# Planner Execution Plan

**Generated:** 2026-09-23 14:22:32
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for the Analysis & Reporter Workflow**

1. **Analysis**: Using the existing 200‑ns production trajectories in the sub‑directories `rep01` and `rep02`, compute the ten required scalar dynamics descriptors for the q13308 – ATP holo complex. Map the ATP‑binding pocket onto q13308 by aligning its sequence to the KAPCA (p17612) consensus pocket (15 Å cutoff) via MAFFT star MSA, and use this mapping for all pocket‑centric metrics (χ₁ statistics, distance, orientation). Calculate: (i) mean ± SD of ATP COM distance to the consensus pocket, (ii) mean ± SD of ATP axis angle relative to the pocket axis, (iii) circular mean ± SD of pocket side‑chain χ₁, (iv) mean ± SD of Cα RMSF for consensus‑mapped residues, (v) mean N‑lobe ↔ C‑lobe DCCM correlation, and (vi) the shared‑reference dihedral PCA scalar `pca_pka_ref_shared_dyn`. Average each descriptor across the two replicates.

2. **Plotting**: Generate full‑trajectory plots (0–200 ns) for ATP COM distance, pocket χ₁, Cα RMSF, and the N↔C DCCM heatmap, ensuring all data points are displayed (no truncation).

3. **Reporting**: Assemble the averaged descriptor values into a concise table, embed the trajectory plots, and produce an HTML report that includes brief literature context for PTK7 and the holo‑ATP state. The report should be ready for integration into the larger comparative study but will contain only the q13308 results. No new simulations, preprocessing, or solvation steps are required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q13308_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
