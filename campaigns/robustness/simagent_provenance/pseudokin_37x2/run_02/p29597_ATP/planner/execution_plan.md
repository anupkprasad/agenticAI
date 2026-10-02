# Planner Execution Plan

**Generated:** 2026-09-23 22:58:24
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

1. **Analysis**  
   *For each of the 37 pre‑existing MD trajectories (two 200 ns replicas per system):*  
   – Calculate the mean and SD of ATP COM distance to the consensus pocket (derived from KAPCA, 15 Å cutoff).  
   – Compute the mean and SD of the ATP orientation angle relative to the pocket axis.  
   – Determine the circular mean and SD of pocket side‑chain χ₁ angles.  
   – Measure mean and SD of RMSF for consensus‑mapped Cα atoms.  
   – Extract the mean correlation of the N‑lobe ↔ C‑lobe DCCM.  
   – Evaluate the shared‑reference dihedral PCA scalar \( \sqrt{d_g^2 + d_c^2 + pc_{rms}^2} \).  
   – Aggregate these ten descriptors across the two replicas (averaged).  

2. **Feature Table & Clustering**  
   *Compile the ten‑descriptor vectors into a single feature matrix, apply Ward hierarchical clustering, and generate:*
   – A dendrogram (full tree) with robust z‑score/IQR scaling.  
   – A heatmap of the clustered feature values, marking a k=4 cut for interpretation.

3. **Reporter**  
   *Produce an HTML report in the directory `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP/reporter/` that includes:*
   – Summary of analysis results for each system.  
   – Embedded dendrogram and heatmap visualizations.  
   – Concise literature context and discussion of the 32 pseudokinases vs. 5 active kinases.  

**Constraints & Conditions**  
- All trajectories are already simulated under the default conditions (amber99sb‑ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl, cubic box with 1.2 nm buffer).  
- Only the components specified by `case_id=protein_with_ligand` (protein + ATP, no crystallographic Mg/ions) are used.  
- No new simulations, preprocessing, or solvation steps are performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
