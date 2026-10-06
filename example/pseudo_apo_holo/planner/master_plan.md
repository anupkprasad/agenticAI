# Multi-Simulation Master Plan

**Generated:** 2026-10-06 10:28:45
**Simulations:** 8
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** no
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

**Goal for the workflow agents**

1. **Preprocessing** – For each of the four PDBs (p21860, q8iv63, q8nb16, q8wz42), extract the protein chain only for the “protein_only” (apo) case and the protein plus ATP and Mg²⁺ for the “protein_with_ligand” (holo) case, discarding all other ligands, ions, and waters.  
2. **Simulation setup** – Generate solvated cubic boxes (1.2 nm buffer) with TIP3P water and 0.15 M NaCl, using AMBER99SB-ILDN force field, for each of the eight systems (apo and holo for each protein). Prepare all required topology, coordinate, MDP, and TPR files for a 1‑ns production run at 310 K and 1 bar.  
3. **HPC** – Submit the eight prepared jobs to the HPC queue, ensuring each job runs the 1‑ns production trajectory.  
4. **Analysis** – For every trajectory compute: backbone RMSD, per‑residue RMSF (with a bar plot for residues 150–200 where present), radius of gyration, COM distance between ATP and the catalytic pocket (holo only), Cα DCCM (including apo vs. holo differences where both exist), and DSSP time evolution for the full protein and residues 150–200.  
5. **Reporter** – Compile overlay plots and statistical tables comparing all systems, retrieve and summarize literature on activation‑loop conformation and allosteric regulation for each protein, and correlate these findings with the simulation results in the final report.

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Protein + ATP + Mg (holo), Protein only (apo).

Example per-sim wording:
For the apo ERBB3 system (label p21860, source p21860.pdb, dir /home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860), preprocess, set up a 1‑ns MD with AMBER99SB-ILDN/TIP3P at 310 K/1 bar, submit to HPC, then analyze backbone RMSD, per‑residue RMSF (including residues 150–200), radius of gyration, Cα DCCM, DSSP time evolution, and produce plots for overlay with other systems. The reporter will gather literature on ERBB3 activation‑loop dynamics and compare to the simulation results. Case requirement: case_id=protein_only Protein only (apo) Preprocess and set up MD simulations for 1 ns with AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, 0.15 M NaCl for all four PDBs (p21860.pdb, q8iv63.pdb, q8nb16.pdb, q8wz42.pdb). Use protein only: exclude ligand and crystallographic ions from the source PDB.

## Simulation inventory

| # | Label | Protein | PDB | Case | Directory |
|---|-------|---------|-----|------|-----------|
| 1 | p21860 | ERBB3 | p21860.pdb | Protein only (apo) | `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860` |
| 2 | p21860_ATP_MG | ERBB3 | p21860.pdb | Protein + ATP + Mg (holo) | `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG` |
| 3 | q8iv63 | VRK3 | q8iv63.pdb | Protein only (apo) | `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63` |
| 4 | q8iv63_ATP_MG | VRK3 | q8iv63.pdb | Protein + ATP + Mg (holo) | `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63_ATP_MG` |
| 5 | q8nb16 | MLKL | q8nb16.pdb | Protein only (apo) | `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8nb16` |
| 6 | q8nb16_ATP_MG | MLKL | q8nb16.pdb | Protein + ATP + Mg (holo) | `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8nb16_ATP_MG` |
| 7 | q8wz42 | TITIN | q8wz42.pdb | Protein only (apo) | `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8wz42` |
| 8 | q8wz42_ATP_MG | TITIN | q8wz42.pdb | Protein + ATP + Mg (holo) | `/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8wz42_ATP_MG` |

## Pre-Combined Plan (before per-sim traj analysis)

_Not requested — skip pre_combined stage._

## Post-Combined Plan (after all per-sim analysis+reporter)

After all per‑simulation analyses and reporters finish, aggregate the standard metric files (rmsd.dat, rmsf.dat, gyration.dat, dccm_heatmap.png, dssp.png, ligand_pocket_distance.csv) across the eight systems, compute overlay plots and statistical tables (mean, std, min, max) for each metric, and generate a combined HTML report that juxtaposes apo vs holo dynamics for each protein, highlights pocket COM shifts, and correlates findings with the retrieved literature.