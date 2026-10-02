# Planner Execution Plan

**Generated:** 2026-09-23 13:32:50
**Phase:** single

## Overview

**Title:** Compiled shared analysis protocol
**Agent sequence:** analysis_agent → reporter_agent
**Subtask:** analysis_only

## Full Plan

**GOAL**
Per-system analysis using the compiled shared analysis protocol. This plan is deterministic (no per-sim LLM tool list).

**USER GOAL**
**Rephrased Goal for Analysis → Reporter Agents**

1. **Analysis**: Using the two already‑generated 200 ns trajectories of the holo kinase q92519 (TRIB2) with ATP ligand (no Mg/ions), compute the ten scalar dynamics descriptors:  
   - ATP COM distance to the consensus pocket (mean & SD)  
   - ATP orientation vs pocket axis (mean & SD)  
   - Pocket side‑chain χ₁ circular mean & SD  
   - Flexibility of consensus‑mapped Cα atoms (mean & SD RMSF)  
   - N‑lobe ↔ C‑lobe DCCM mean  
   - Shared‑reference PCA dynamics scalar relative to KAPCA.  
   The consensus pocket is defined by mapping KAPCA residues onto q92519 via a global sequence alignment (MAFFT/star MSA).  

2. **Reporting**: Average the descriptors across the two replicates, generate plots of the full 200 ns trajectories, and compile an HTML report that presents the descriptor table, the plots, and a concise literature context for TRIB2–ATP interactions.

**Constraints**: Only the analysis and reporter stages are performed; no preprocessing, simulation setup, or new MD runs are requested. The study is limited to the q92519_ATP system with the specified components (protein + ATP ligand, excluding Mg/ions).

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q92519_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
