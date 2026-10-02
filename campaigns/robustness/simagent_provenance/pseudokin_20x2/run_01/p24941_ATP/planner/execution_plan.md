# Planner Execution Plan

**Generated:** 2026-09-23 13:04:28
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal (analysis → reporter only)**  

1. Analyze the two 200 ns replica trajectories of the p24941 ATP holo complex (located in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p24941_ATP/rep01` and `rep02`).  
2. Compute the ten scalar dynamics descriptors for each replica:  
   - ATP COM distance to the consensus pocket (mean & SD)  
   - ATP orientation vs. pocket axis (mean & SD)  
   - Pocket side‑chain χ₁ circular mean & SD  
   - Flexibility of consensus‑mapped Cα atoms (mean & SD RMSF)  
   - N‑lobe ↔ C‑lobe DCCM mean correlation  
   - Shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar  
3. Average the descriptors across the two replicates to obtain the final values for p24941.  
4. Generate full‑trajectory plots (200 ns) for both replicas and include them in the output.  
5. Compile an HTML report that presents the averaged descriptor table, the trajectory plots, and a brief literature context for the CDK2 holo state.  

**Constraints / Special Requirements**  
- Only the protein and ATP ligand are considered; any crystallographic Mg/ions and water present in the trajectories are ignored in the descriptor calculations.  
- No new simulations, preprocessing, or equilibration steps are performed.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p24941_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
