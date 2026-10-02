# Multi-Simulation Master Plan

**Generated:** 2026-09-22 17:34:42
**Simulations:** 10
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** yes
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

Preprocess the ten ATP‑bound PDBs by retaining only the protein, ligand, and ion atoms, then solvate with TIP3P, add 0.15 M NaCl, and generate GROMACS input files (amber99sb‑ildn, cubic box 1.2 nm).  
Run two independent 200‑ns production replicas for each system at 310 K/1 bar, ensuring the full 200‑ns trajectory is retained.  
After completion, map the KAPCA (p17612) ATP‑binding pocket (residues within 15 Å of ATP) onto all other proteins using a global MAFFT/star MSA, and plot both the global MSA and pocket/high‑consensus MSA panels.  
Compute the ten scalar dynamics descriptors from both replicates (and average across replicates) for every system, then assemble them into a single feature table.  
Apply Ward hierarchical clustering, generate a dendrogram and feature‑heatmap with robust z‑score/IQR scaling, and produce a combined HTML report with brief literature context and a k = 4 cut for interpretation.

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Full end-to-end MD simulation of protein–ATP holo complexes.

Example per-sim wording:
Simulation p17612_ATP (KAPCA; Full end-to-end MD simulation of protein–ATP holo complexes; source p17612.pdb; working directory /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p17612_ATP). Run preprocessing, GROMACS setup with AMBER99SB-ILDN/TIP3P, 310 K, 1 bar, 0.15 M NaCl, two 200 ns production replicates per system, followed by analysis and clustering as specified. Download structure from auto for UniProt P17612 if p17612.pdb is not present. Shared per-simulation workflow intent: Run these analyses: ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF. Workflow steps: preprocess -> simsetup -> hpcjob -> analysis -> reporter. Write outputs under /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p17612_ATP/analysis/ using standard basenames (no label prefix). After analysis, prepare a concise HTML report for this simulation under /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p17612_ATP/reporter/. Family-modular descriptors required for every system: ATP COM distance to the consensus pocket, pocket-axis orientation, consensus Cα RMSF mean/std, pocket χ₁ circular mean, N-lobe vs C-lobe DCCM, and dihedral PCA landscape entropy. I have 10 human protein–ATP holo structures in given working directory
(one PDB per system), spanning active kinases and pseudokinases.
Please run a full end-to-end comparative MD study on all of them.

Systems (UniProt id : protein name):
  p17612:KAPCA, o60674:JAK2, p24941:CDK2, q8ivt5:KSR1, q13418:ILK, p00533:EGFR,
  p23458:JAK1, q6vab6:KSR2, q92519:TRIB2, q9y243:AKT3

For each complex, preprocess the structure and set up GROMACS with
AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, and 0.15 M NaCl.
Run two independent 200 ns production MD replicates per system, wait for all
simulations to finish, then analyze and plot the full 200 ns of every
trajectory (do not truncate to a shorter window).

Use KAPCA (p17612) as the reference to define the ATP-binding pocket
(residues within 15 Å of ATP, unless a different cutoff is stated), map that
pocket onto the other proteins with a global… Case requirement: case_id=protein_with_ligand Include the ligand (e.g. ATP) but exclude crystallographic Mg/ions from the source PDB.

## Simulation inventory

| # | Label | Protein | PDB | Case | Directory |
|---|-------|---------|-----|------|-----------|
| 1 | p17612_ATP | KAPCA | p17612.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p17612_ATP` |
| 2 | o60674_ATP | JAK2 | o60674.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/o60674_ATP` |
| 3 | p24941_ATP | CDK2 | p24941.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p24941_ATP` |
| 4 | q8ivt5_ATP | KSR1 | q8ivt5.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q8ivt5_ATP` |
| 5 | q13418_ATP | ILK | q13418.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q13418_ATP` |
| 6 | p00533_ATP | EGFR | p00533.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p00533_ATP` |
| 7 | p23458_ATP | JAK1 | p23458.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p23458_ATP` |
| 8 | q6vab6_ATP | KSR2 | q6vab6.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q6vab6_ATP` |
| 9 | q92519_ATP | TRIB2 | q92519.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q92519_ATP` |
| 10 | q9y243_ATP | AKT3 | q9y243.pdb | Full end-to-end MD simulation of protein–ATP holo complexes | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q9y243_ATP` |

## Pre-Combined Plan (before per-sim traj analysis)

Before any per‑simulation analysis, perform cross‑simulation preprocessing: 1) Identify the ATP‑binding pocket in KAPCA (p17612) as residues within 15 Å of ATP. 2) Build a global MAFFT alignment of all ten holo structures and map the pocket residues onto each protein, generating a consensus pocket list. 3) Export the global mapped alignment and consensus pocket mapping as JSON files into base/cross_sim/. 4) These artifacts will be used by each per‑simulation analysis to compute the ten scalar descriptors.

## Post-Combined Plan (after all per-sim analysis+reporter)

After all per‑simulation analysis and reporter stages finish, collect the ten scalar descriptors from each system, assemble them into a single feature table, apply robust z‑score/IQR scaling, and run Ward hierarchical clustering. Generate a dendrogram and a feature‑heatmap panel, marking a k=4 cut for interpretation. Finally, produce a combined HTML report that summarizes the clustering, includes literature context, and presents the key plots and tables.