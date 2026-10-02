# Multi-Simulation Master Plan

**Generated:** 2026-09-23 17:51:35
**Simulations:** 37
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** yes
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

**Rephrased Goal (3‑6 sentences)**  

1. **Preprocessing**: For each of the 37 PDBs, extract only the protein, ligand (ATP), and ions, excluding any water molecules.  
2. **Simulation Setup (simsetup)**: Build GROMACS inputs (topology, coordinates, .mdp, and .tpr) using AMBER99SB‑ILDN, TIP3P, 310 K, 1 bar, 0.15 M NaCl, cubic box with 1.2 nm buffer; solvate and add ions to neutralise the system.  
3. **HPC**: Submit two independent 200‑ns production MD replicates per system (74 trajectories total), monitor, and confirm all 200‑ns trajectories are fully generated (no truncation).  
4. **Analysis**: Map the ATP‑binding pocket from KAPCA (p17612) onto all proteins via a MAFFT/star MSA; plot the global and pocket‑mapped MSAs. Compute, for each system (averaged over the two replicates), the ten scalar descriptors: ATP COM distance statistics, ATP‑pocket axis angles, pocket χ₁ circular mean & std, consensus‑mapped Cα RMSF mean & std, N‑lobe ↔ C‑lobe DCCM mean, and shared‑reference dihedral PCA metric. Assemble a feature table, perform Ward hierarchical clustering, and generate a dendrogram and IQR‑scaled heatmap (optionally marking a k = 4 cut).  
5. **Reporter**: Compile all results, plots, and a brief literature context into a single HTML report, ensuring the full 200‑ns data and all ten descriptors are included.

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Protein–ATP holo structure.

## Simulation inventory

| # | Label | Protein | PDB | Case | Directory |
|---|-------|---------|-----|------|-----------|
| 1 | o15197_ATP | EPHB6 | o15197.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o15197_ATP` |
| 2 | o43187_ATP | IRAK2 | o43187.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o43187_ATP` |
| 3 | o60674_ATP | JAK2 | o60674.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o60674_ATP` |
| 4 | p00533_ATP | EGFR | p00533.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p00533_ATP` |
| 5 | p17612_ATP | KAPCA | p17612.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p17612_ATP` |
| 6 | p21860_ATP | ERBB3 | p21860.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p21860_ATP` |
| 7 | p23458_ATP | JAK1 | p23458.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p23458_ATP` |
| 8 | p24941_ATP | CDK2 | p24941.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p24941_ATP` |
| 9 | p25092_ATP | GUC2C | p25092.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p25092_ATP` |
| 10 | p28482_ATP | MK01 | p28482.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p28482_ATP` |
| 11 | p29597_ATP | TYK2 | p29597.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p29597_ATP` |
| 12 | p51841_ATP | GUC2F | p51841.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p51841_ATP` |
| 13 | p52333_ATP | JAK3 | p52333.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p52333_ATP` |
| 14 | q05823_ATP | RN5A | q05823.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q05823_ATP` |
| 15 | q13308_ATP | PTK7 | q13308.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13308_ATP` |
| 16 | q13418_ATP | ILK | q13418.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13418_ATP` |
| 17 | q58a45_ATP | PAN3 | q58a45.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q58a45_ATP` |
| 18 | q5jzy3_ATP | EPHAA | q5jzy3.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q5jzy3_ATP` |
| 19 | q6vab6_ATP | KSR2 | q6vab6.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q6vab6_ATP` |
| 20 | q7rtn6_ATP | STRAA | q7rtn6.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7rtn6_ATP` |
| 21 | q7z7a4_ATP | PXK | q7z7a4.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7z7a4_ATP` |
| 22 | q8iv63_ATP | VRK3 | q8iv63.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8iv63_ATP` |
| 23 | q8ivt5_ATP | KSR1 | q8ivt5.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ivt5_ATP` |
| 24 | q8nb16_ATP | MLKL | q8nb16.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8nb16_ATP` |
| 25 | q8ncb2_ATP | CAMKV | q8ncb2.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ncb2_ATP` |
| 26 | q8ne28_ATP | STKL1 | q8ne28.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ne28_ATP` |
| 27 | q8tea7_ATP | TBCK | q8tea7.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8tea7_ATP` |
| 28 | q8wz42_ATP | TITIN | q8wz42.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8wz42_ATP` |
| 29 | q92519_ATP | TRIB2 | q92519.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q92519_ATP` |
| 30 | q96c45_ATP | ULK4 | q96c45.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q96c45_ATP` |
| 31 | q96qs6_ATP | PSKH2 | q96qs6.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q96qs6_ATP` |
| 32 | q9bxu1_ATP | STK31 | q9bxu1.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9bxu1_ATP` |
| 33 | q9c0k7_ATP | STRAB | q9c0k7.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9c0k7_ATP` |
| 34 | q9nsy0_ATP | NRBP2 | q9nsy0.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9nsy0_ATP` |
| 35 | q9uhy1_ATP | NRBP | q9uhy1.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9uhy1_ATP` |
| 36 | q9y243_ATP | AKT3 | q9y243.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9y243_ATP` |
| 37 | q9y616_ATP | IRAK3 | q9y616.pdb | Protein–ATP holo structure | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9y616_ATP` |

## Pre-Combined Plan (before per-sim traj analysis)

Before any per‑simulation analysis, perform the following cross‑simulation steps:
1. Build a global MAFFT alignment of all 37 holo kinase sequences using the KAPCA (p17612) structure as the reference. Export the alignment and a consensus sequence.
2. Define the ATP‑binding pocket of KAPCA as all residues within 15 Å of the ATP ligand. Map this pocket onto each protein via the consensus alignment to generate a per‑system pocket residue list (pocket_mapped.json).
3. For each system, create a consensus‑mapped Cα alignment file (alignment_json) that aligns all proteins to the consensus sequence, enabling residue‑level comparisons.
4. Fit a shared‑reference PCA model on the KAPCA trajectory (dihedral space) and project all other trajectories onto this model, producing the shared‑reference dihedral PCA metrics.
5. Store all mapping and alignment artifacts in the base/cross_sim/ directory for later use by the per‑simulation analysis tools.
These steps ensure that every simulation has a common residue mapping and reference frame for descriptor calculation.

## Post-Combined Plan (after all per-sim analysis+reporter)

After all per‑simulation analysis and reporter generation:
1. Collect the ten scalar descriptors from each system’s analysis/avg/ directory into a single feature table (CSV). Apply robust z‑score or IQR scaling.
2. Perform Ward hierarchical clustering on the scaled feature matrix.
3. Generate a dendrogram image and a heatmap of the scaled features, marking a k=4 cut for interpretation but retaining the full tree.
4. Compile the clustering results, dendrogram, heatmap, and all per‑system reports into a single combined HTML report using generate_combined_html_report.
5. Include a brief literature context section summarizing known pseudokinase vs active kinase behavior.
6. Output the final report to the campaign root as combined_report.html.