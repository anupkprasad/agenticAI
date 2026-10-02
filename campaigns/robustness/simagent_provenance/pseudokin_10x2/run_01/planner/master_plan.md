# Multi-Simulation Master Plan

**Generated:** 2026-09-22 16:24:48
**Simulations:** 10
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** yes
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

**Rephrased Goal for the Workflow Agents**

1. **Preprocessing** – Extract the protein, ATP ligand, and all metal ions from each PDB; retain only these components, remove water and other non‑protein atoms, and convert the coordinates to a single-chain format suitable for GROMACS.  
2. **Simulation Setup** – Generate AMBER99SB‑ILDN topology, solvate in a cubic TIP3P box with 1.2 nm buffer, add 0.15 M NaCl, set 310 K/1 bar, and create two independent 200 ns production TPR files per system.  
3. **HPC Execution** – Submit the 20 production jobs to the HPC queue, ensuring that all 200 ns trajectories are completed before proceeding.  
4. **Analysis** – For each of the 10 proteins (using the KAPCA pocket definition and a MAFFT‑derived MSA), compute the ten scalar descriptors from both replicates, average across replicas, and assemble them into a feature table; then perform Ward hierarchical clustering, produce a dendrogram and heatmap (z‑score/IQR scaling), and annotate a k = 4 cut.  
5. **Reporting** – Compile an HTML report that includes the literature context, the full dendrogram, the heatmap, and a concise interpretation of the clustering results.

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Protein–ATP holo structures.

Example per-sim wording:
For the KAPCA holo kinase system (label=p17612_ATP, source=p17612.pdb, dir=/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p17612_ATP, case=Protein–ATP holo structures), perform preprocessing, simulation setup, HPC job, analysis to compute the ten scalar dynamics descriptors (ATP COM distance, orientation, pocket χ1, RMSF, DCCM, dihedral PCA, etc.) and generate the required plots, then produce a report. Case requirement: case_id=protein_with_ligand Run two independent 200 ns production MD replicates per system with AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, 0.15 M NaCl. Include the ligand (e.g. ATP) but exclude crystallographic Mg/ions from the source PDB.

## Simulation inventory

| # | Label | Protein | PDB | Case | Directory |
|---|-------|---------|-----|------|-----------|
| 1 | p17612_ATP | KAPCA | p17612.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p17612_ATP` |
| 2 | o60674_ATP | JAK2 | o60674.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/o60674_ATP` |
| 3 | p24941_ATP | CDK2 | p24941.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p24941_ATP` |
| 4 | q8ivt5_ATP | KSR1 | q8ivt5.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q8ivt5_ATP` |
| 5 | q13418_ATP | ILK | q13418.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q13418_ATP` |
| 6 | p00533_ATP | EGFR | p00533.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p00533_ATP` |
| 7 | p23458_ATP | JAK1 | p23458.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/p23458_ATP` |
| 8 | q6vab6_ATP | KSR2 | q6vab6.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q6vab6_ATP` |
| 9 | q92519_ATP | TRIB2 | q92519.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q92519_ATP` |
| 10 | q9y243_ATP | AKT3 | q9y243.pdb | Protein–ATP holo structures | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/q9y243_ATP` |

## Pre-Combined Plan (before per-sim traj analysis)

First, define the ATP‑binding pocket in KAPCA (p17612) by selecting all residues within 15 Å of the ATP ligand. Map this pocket onto all other proteins using a global MAFFT MSA and generate consensus residue lists. Build a consensus sequence alignment and consensus pocket mapping, storing the mapping JSONs and alignment files in base/cross_sim/. These artifacts will be used for per‑simulation analysis.

## Post-Combined Plan (after all per-sim analysis+reporter)

Collect the ten scalar descriptor files from each simulation, assemble them into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a heatmap with robust z‑score/IQR scaling. Annotate a k=4 cut in the dendrogram. Produce a combined HTML report that includes literature context, the dendrogram, the heatmap, and a concise interpretation of the clustering results.