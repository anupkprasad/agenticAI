# Planner Execution Plan

**Generated:** 2026-09-22 17:15:38
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

1. **Data Inputs**: Use the existing 200 ns production trajectories from the two EGFR‑ATP replicates (rep01, rep02) located in `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p00533_ATP`. The system contains the protein and ATP ligand only; crystallographic Mg²⁺ ions are excluded.

2. **Analysis Tasks**  
   - Identify the ATP‑binding pocket as all residues within 15 Å of ATP in the KAPCA reference (p17612) and map this pocket onto EGFR via global sequence alignment.  
   - For each replicate, compute the ten required scalar descriptors: (i) mean and SD of ATP COM distance to the consensus pocket; (ii) mean and SD of ATP orientation vs the pocket axis; (iii) circular mean and SD of pocket side‑chain χ₁ angles; (iv) mean and SD of RMSF of consensus‑mapped Cα atoms; (v) mean DCCM correlation between N‑lobe and C‑lobe; (vi) shared‑reference dihedral PCA distance (√(d_g² + d_c² + pc_rms²)).  
   - Average the descriptor values over the two replicates to obtain a single feature vector for EGFR.

3. **Output Generation**  
   - Produce time‑series plots for ATP distance, orientation, pocket χ₁ distribution, and RMSF; generate a DCCM heatmap and a PCA scree/trajectory plot.  
   - Compile the averaged descriptor vector into a feature table (CSV/TSV).  
   - Create an HTML report that includes the plots, the feature table, a brief literature context for EGFR ATP binding, and, where possible, a hierarchical clustering dendrogram and heatmap (trivial for a single system, but included for consistency).  

4. **Constraints**  
   - All analyses must be performed solely on the existing trajectory data; no new preprocessing, solvation, or simulation steps are to be performed.  
   - Use only the protein and ATP ligand; no Mg²⁺ or other ions are considered in the analysis.  
   - Follow the default simulation conditions (AMBER99SB‑ILDN, TIP3P, 310 K, 1 bar, 0.15 M NaCl) implicitly, as they are already satisfied by the trajectories.

**EXECUTION SEQUENCE**
The Analysis Agent wraps each `hpc/repXX` trajectory, then runs the required calculations (calculate_consensus_pocket_metrics, calculate_consensus_torsions, calculate_consensus_rmsf_features, calculate_consensus_dccm_features) with that replica's topology/trajectory. Metrics are written to `analysis/repXX/` and averaged in `analysis/avg/`.

The Reporter Agent then writes the per-system HTML report.

Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p00533_ATP
Do not re-run preprocess, setup, or HPC. Do not invent placeholder tools.
