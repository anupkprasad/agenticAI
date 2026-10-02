# Planner Execution Plan

**Generated:** 2026-09-23 16:14:13
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis → Reporter Workflow**

1. **Analysis**  
   - Load the 200 ns trajectories of all 20 protein–ATP holo complexes (protein + ATP, no crystallographic ions).  
   - Define the ATP‑binding pocket for each system by mapping the KAPCA (p17612) pocket (residues within 15 Å of ATP) onto each protein via a global MAFFT alignment.  
   - For each system and each of the two independent replicates, compute the ten scalar dynamics descriptors:  
     1. ATP COM distance to consensus pocket – mean  
     2. ATP COM distance to consensus pocket – std dev  
     3. ATP orientation vs pocket axis – mean angle  
     4. ATP orientation vs pocket axis – std dev  
     5. Pocket side‑chain χ₁ circular mean  
     6. Pocket side‑chain χ₁ circular std dev  
     7. Consensus‑mapped Cα RMSF – mean  
     8. Consensus‑mapped Cα RMSF – std dev  
     9. N‑lobe ↔ C‑lobe DCCM mean correlation  
    10. Shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar (pca_pka_ref_shared_dyn).  
   - Average each descriptor over the two replicates.  
   - Assemble the resulting 20 × 10 feature matrix in `/home/akp66103/.../q05823_ATP/analysis/`.  
   - Perform Ward hierarchical clustering on the feature table, generate a dendrogram and a robust‑z‑score/​IQR‑scaled heatmap panel, and save them in the same analysis directory.

2. **Reporter**  
   - Compile the dendrogram, heatmap, feature table, and a concise literature context for each of the 20 systems into a single HTML report.  
   - Place the report in `/home/akp66103/.../q05823_ATP/reporter/`.  

All outputs must be created without initiating any new preprocessing, simulation setup, or HPC submissions.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q05823_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
