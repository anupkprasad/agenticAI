# Planner Execution Plan

**Generated:** 2026-09-23 18:46:09
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

1. **Analysis**: For each of the 37 existing 200 ns trajectories (protein–ATP holo, case_id = protein_with_ligand), compute the following per‑replica and replicate‑averaged metrics:  
   - ligand pocket distance;  
   - consensus DCCM, consensus RMSF, consensus torsions;  
   - full DCCM;  
   - dihedral PCA;  
   - nearby contacts;  
   - protein RMSF;  
   - ATP COM distance to the KAPCA‑defined consensus pocket (mean & std);  
   - ATP orientation vs pocket axis (mean & std of axis angle);  
   - pocket side‑chain χ₁ circular mean & std;  
   - consensus‑mapped Cα RMSF mean & std;  
   - N‑lobe ↔ C‑lobe DCCM mean correlation;  
   - shared‑reference dihedral PCA entropy.  
   Output each metric as a standard‑named file in `/analysis/` with no label prefixes.

2. **Clustering**: Assemble the ten scalar descriptors into a single feature table for all systems, apply Ward hierarchical clustering, and generate a dendrogram + feature‑heatmap (robust z‑score / IQR scaling) in the same report.

3. **Reporter**: Produce a concise HTML report in `/reporter/` that (i) summarizes the computed metrics per system, (ii) includes the dendrogram and heatmap, (iii) provides brief literature context for pseudokinase vs. active kinase behavior, and (iv) marks a k = 4 cut for interpretation while still presenting the full tree.  

**Constraints**:  
- Do not perform any preprocessing, simulation setup, or new trajectory generation; use the already‑existing trajectories.  
- All analyses must adhere to the default simulation conditions (amber99sb‑ildn, tip3p, 310 K, 1 bar, 0.15 M NaCl, cubic box with 1.2 nm buffer).  
- Only include the protein and ATP ligand; exclude crystallographic Mg/ions and any other ions unless explicitly required.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p00533_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
