# Multi-Simulation Master Plan

**Generated:** 2026-09-23 11:10:01
**Simulations:** 5
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** yes
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

**Rephrased Goal (Workflow‑Scope‑Specific)**  

1. **Preprocessing** – For each of the five PDBs (p17612, o60674, p24941, q8ivt5, q13418) extract only the protein, ligand (ATP), and metal ions (Mg²⁺) components, removing all water molecules.  
2. **Simulation Setup** – Generate amber99sb‑ildn topology, solvate each system in a cubic TIP3P box with a 1.2 nm buffer, add 0.15 M NaCl, then produce the full GROMACS input files (gro, top, .mdp, tpr).  
3. **HPC Execution** – Run two independent 200 ns production MD replicates per system (total 10 simulations) at 310 K, 1 bar, using the standard GROMACS protocol (energy minimization, NVT/NPT equilibration, production).  
4. **Analysis** –  
   * Define the ATP‑binding pocket of KAPCA (p17612) as residues within 15 Å of ATP, map these residues onto the other proteins via a global MAFFT MSA, and plot both the global MSA and pocket‑specific MSA.  
   * For each replicate, compute the ten scalar descriptors listed (ATP COM distances, orientation angles, pocket χ₁ statistics, Cα RMSF, N‑/C‑lobe DCCM mean, shared‑reference dihedral PCA metric).  
   * Average the descriptors across the two replicates per system, assemble them into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a feature‑heatmap (robust z‑score/IQR scaling).  
5. **Reporter** – Produce a single HTML report that includes the dendrogram, heatmap, the MSA panels, a literature context summary, and a highlighted k = 4 cut (while still showing the full tree).  

**Constraints** – Use amber99sb‑ildn force field, TIP3P water, 310 K temperature, 1 bar pressure, 0.15 M NaCl, cubic box with 1.2 nm buffer; all systems must be solvated (no vacuum). No additional steps beyond those listed are required.

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Protein–ATP holo.

Example per-sim wording:
Simulation p17612_ATP (KAPCA; Protein–ATP holo; source p17612.pdb; working directory /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p17612_ATP). Run full end‑to‑end MD pipeline for each of the five protein–ATP holo structures Download structure from auto for UniProt P17612 if p17612.pdb is not present. Shared per-simulation workflow intent: Run these analyses: ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF. Workflow steps: preprocess -> simsetup -> hpcjob -> analysis -> reporter. Write outputs under /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p17612_ATP/analysis/ using standard basenames (no label prefix). After analysis, prepare a concise HTML report for this simulation under /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p17612_ATP/reporter/. Family-modular descriptors required for every system: ATP COM distance to the consensus pocket, pocket-axis orientation, consensus Cα RMSF mean/std, pocket χ₁ circular mean, N-lobe vs C-lobe DCCM, and dihedral PCA landscape entropy. I have 5 human protein–ATP holo structures in the given working directory
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
| 1 | p17612_ATP | KAPCA | p17612.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p17612_ATP` |
| 2 | o60674_ATP | JAK2 | o60674.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/o60674_ATP` |
| 3 | p24941_ATP | CDK2 | p24941.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p24941_ATP` |
| 4 | q8ivt5_ATP | KSR1 | q8ivt5.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/q8ivt5_ATP` |
| 5 | q13418_ATP | ILK | q13418.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/q13418_ATP` |

## Pre-Combined Plan (before per-sim traj analysis)

Before any per‑simulation analysis, perform cross‑simulation steps: (1) identify the ATP‑binding pocket residues in the KAPCA reference (within 15 Å of ATP), (2) build a global MAFFT MSA of all five proteins, (3) map the reference pocket onto each system via the MSA, and (4) generate the consensus residue mapping JSONs. These artifacts will be stored in the base/cross_sim/ directory and used by each simulation’s analysis stage.

## Post-Combined Plan (after all per-sim analysis+reporter)

After all simulations have completed and each has produced the ten scalar descriptors, aggregate the descriptor tables into a single feature matrix, apply Ward hierarchical clustering, generate a dendrogram and robust z‑score/IQR‑scaled heatmap, and compile a combined HTML report that includes the MSA panels, the clustering visualizations, and a brief literature context. The report will be written to the campaign root.