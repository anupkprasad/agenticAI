# Multi-Simulation Master Plan

**Generated:** 2026-09-23 10:29:12
**Simulations:** 5
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** yes
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

**Rephrased Goal (Preprocessing → Simsetup → HPC → Analysis → Reporter)**  

1. Preprocess the five PDBs (p17612, o60674, p24941, q8ivt5, q13418) to retain only the protein, ATP ligand, and any ions (exclude water).  
2. Build GROMACS input files (topology, coordinates, MDP, TPR) for each system using amber99sb‑ildn, TIP3P water, 310 K, 1 bar, 0.15 M NaCl, a cubic box with 1.2 nm buffer, and generate two independent 200 ns production replicas per system on the HPC.  
3. After all trajectories finish, compute for each system the ten specified scalar descriptors (averaged across the two replicas), map the 15 Å ATP‑binding pocket of KAPCA onto the others via MAFFT global MSA, and construct both the full MSA and pocket‑specific MSA plots.  
4. Assemble the descriptor matrix, perform Ward hierarchical clustering, and output a dendrogram with a k = 4 cut plus a robustly scaled feature‑heatmap.  
5. Compile all results, plots, and a brief literature context into a single HTML report.  

All simulation conditions follow the default pipeline (amber99sb‑ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl, cubic box).

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Full end‑to‑end MD study of protein–ATP holo complexes.

Example per-sim wording:
Simulation p17612_ATP (KAPCA; Full end‑to‑end MD study of protein–ATP holo complexes; source p17612.pdb; working directory /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p17612_ATP). Preprocess each holo PDB, set up GROMACS with AMBER99SB-ILDN/TIP3P, 310 K, 1 bar, 0.15 M NaCl, run two independent 200 ns production replicates, analyze the full trajectories, extract the ten scalar descriptors, assemble the feature table, perform Ward hierarchical clustering, and generate the dendrogram, heatmap, and HTML report. Download structure from auto for UniProt P17612 if p17612.pdb is not present. Shared per-simulation workflow intent: Run these analyses: ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF. Workflow steps: preprocess -> simsetup -> hpcjob -> analysis -> reporter. Write outputs under /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p17612_ATP/analysis/ using standard basenames (no label prefix). After analysis, prepare a concise HTML report for this simulation under /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p17612_ATP/reporter/. Family-modular descriptors required for every system: ATP COM distance to the consensus pocket, pocket-axis orientation, consensus Cα RMSF mean/std, pocket χ₁ circular mean, N-lobe vs C-lobe DCCM, and dihedral PCA landscape entropy. I have 5 human protein–ATP holo structures in the given working directory
(one PDB per system), spanning active kinases and pseudokinases.
Please run a full end-to-end comparative MD study on all of them.

Systems (UniProt id : protein name):
  p17612:KAPCA, o60674:JAK2, p24941:CDK2, q8ivt5:KSR1, q13418:ILK

For each complex, preprocess the structure and set up GROMACS with
AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, and 0.15 M NaCl.
Run two independent 200 ns production MD replicates per system, wait for all
simulations to finish, then analyze and plot the full 200 ns of every
trajectory (do not truncate to a shorter window).

Use KAPCA (p17612) as the reference to define the ATP-binding pocket
(residues within 15 Å of ATP, unless a different cutoff is stated), map that
pocket onto the other proteins with a global sequence alignment
(MAFFT / star MSA), and plot both the global MSA and… Case requirement: case_id=protein_with_ligand Include the ligand (e.g. ATP) but exclude crystallographic Mg/ions from the source PDB.

## Simulation inventory

| # | Label | Protein | PDB | Case | Directory |
|---|-------|---------|-----|------|-----------|
| 1 | p17612_ATP | KAPCA | p17612.pdb | Full end‑to‑end MD study of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p17612_ATP` |
| 2 | o60674_ATP | JAK2 | o60674.pdb | Full end‑to‑end MD study of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/o60674_ATP` |
| 3 | p24941_ATP | CDK2 | p24941.pdb | Full end‑to‑end MD study of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p24941_ATP` |
| 4 | q8ivt5_ATP | KSR1 | q8ivt5.pdb | Full end‑to‑end MD study of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/q8ivt5_ATP` |
| 5 | q13418_ATP | ILK | q13418.pdb | Full end‑to‑end MD study of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/q13418_ATP` |

## Pre-Combined Plan (before per-sim traj analysis)

Before any per‑simulation analysis, perform the shared cross‑simulation setup:
1. Use the KAPCA (p17612) holo structure as the reference. Run `define_reference_consensus_pocket` to identify residues within 15 Å of ATP, producing a pocket definition JSON.
2. For each of the other four proteins, run `define_pocket_mapped_residues` to map the reference pocket onto their sequences via the global MAFFT alignment, generating per‑system pocket‑mapped residue lists.
3. Build a global MAFFT alignment of all five sequences with `build_global_mapped_alignment`, exporting the full MSA and the consensus columns.
4. Store all mapping artifacts (pocket JSONs, alignment JSONs, consensus residue CSVs) in the base/cross_sim/ directory for later use by the per‑simulation analysis tools.
5. Verify that each system’s pocket mapping JSON contains the required residue indices for the subsequent `calculate_consensus_pocket_metrics` and `calculate_consensus_torsions` calls.

## Post-Combined Plan (after all per-sim analysis+reporter)

After all per‑simulation analysis and individual reports are complete:
1. Collect the ten‑descriptor CSV files from each system’s analysis folder using `collect_metric_files`.
2. Merge them into a single feature table with `compute_comparison_table`, computing mean, std, min, max per descriptor.
3. Apply robust z‑score/IQR scaling to the feature matrix.
4. Perform Ward hierarchical clustering with `cluster_classification_features`, generating a dendrogram and a heatmap of the scaled descriptors.
5. Mark a k=4 cut on the dendrogram for interpretation but retain the full tree.
6. Compile all plots, the dendrogram, heatmap, and a brief literature context into a single HTML report via `generate_combined_html_report`.
7. Store the report and all intermediate artifacts in the campaign root for review.