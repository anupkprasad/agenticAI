# Planner Execution Plan

**Generated:** 2026-09-23 15:06:07
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
   - For each of the 20 human protein–ATP holo structures (UniProt ids: p17612, o60674, p24941, q8ivt5, q13418, p00533, p23458, q6vab6, q92519, q9y243, o15197, o43187, p21860, p25092, p28482, p29597, p51841, p52333, q05823, q13308) process the existing 200 ns production trajectories (two independent replicates).  
   - Map the ATP‑binding pocket defined in KAPCA (p17612) onto each protein using a global MAFFT alignment, then generate both the full‑sequence MSA and a high‑consensus pocket‑MSA panel.  
   - Compute the ten scalar dynamics descriptors (mean/std of ATP COM distance to pocket, mean/std of ATP–pocket axis angle, χ₁ circular mean/std for pocket residues, mean/std of consensus‑mapped Cα RMSF, mean N‑lobe↔C‑lobe DCCM, and shared‑reference dihedral PCA entropy) by averaging over the two replicates.  
   - Store each descriptor set in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p17612_ATP/analysis/` with standard basenames (no label prefixes).  
   - Assemble all descriptor values into a single feature table, perform Ward hierarchical clustering (robust z‑score/IQR scaling), and generate a dendrogram plus a feature‑heatmap panel.

2. **Reporter**  
   - Produce a combined HTML report in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p17612_ATP/reporter/` that includes: literature context for protein–ATP holo kinases, the generated MSA panels, the dendrogram with a highlighted k = 4 cut (but still displaying the full tree), and the feature‑heatmap.  
   - All outputs must respect the `protein_with_ligand` case_id: include ATP but exclude crystallographic Mg/ions from the source PDBs.  
   - No new preprocessing, simulation setup, or trajectory generation is performed—analysis is confined to the existing 200 ns data.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p17612_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
