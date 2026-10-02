# Planner Execution Plan

**Generated:** 2026-09-23 23:16:46
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis & Reporter Agents**

1. For each of the 37 holo PDBs (protein + ATP, no crystallographic ions), use the existing 200‑ns trajectories in the *rep01* and *rep02* directories to compute the ten scalar descriptors (ATP COM distance mean/std, ATP–pocket orientation mean/std, pocket χ₁ mean/std, Cα RMSF mean/std, N‑lobe↔C‑lobe DCCM mean, shared‑reference dihedral PCA entropy).  
2. Map each protein’s ATP‑binding pocket onto the KAPCA consensus pocket (within 15 Å of ATP), generate the global MSA and pocket‑specific MSA panels, and use these to define the residues for the RMSF and DCCM calculations.  
3. Assemble the descriptor matrix (37 × 10), apply Ward hierarchical clustering (robust z‑score/IQR scaling), and produce a dendrogram with a k = 4 cut plus a feature‑heatmap; output all analysis files to  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP/analysis/`.  
4. Generate a concise HTML report summarizing the results, literature context, and clustering interpretation, and store it under  
   `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP/reporter/`.  

All analyses must respect the `case_id=protein_with_ligand` directive (include ATP, exclude crystallographic Mg/ions) and use the standard simulation conditions (amber99sb-ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl, cubic box with 1.2 nm buffer).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
