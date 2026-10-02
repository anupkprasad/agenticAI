# Multi-Simulation Master Plan

**Generated:** 2026-09-23 21:20:46
**Simulations:** 37
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** yes
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

**Rephrased Goal for the Workflow Agents**

1. **Preprocessing** – Extract the protein, ligand (ATP), and ion (MG⁺) atoms from each of the 37 PDB files (water omitted) and prepare the structures for GROMACS input.  
2. **Simulation Setup** – Build solvated cubic boxes (1.2 nm buffer), add 0.15 M NaCl, and generate GROMACS topology, mdp, and tpr files using amber99sb‑ildn and TIP3P.  
3. **HPC Execution** – Submit two independent 200 ns production MD runs per system (total 74 trajectories), monitor completion, and collect all trajectories.  
4. **Analysis** – Map the ATP‑binding pocket of KAPCA (p17612) onto each protein via MAFFT MSA; compute the ten scalar descriptors (ATP COM distances, orientation angles, χ₁ statistics, RMSF, DCCM, dihedral‑PCA metric) for each replicate and average across replicates. Assemble a feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a z‑score/IQR‑scaled heatmap.  
5. **Reporter** – Produce a single HTML report that includes a literature context, the full dendrogram, the heatmap, and a brief interpretation marking a k = 4 cut, while also providing the complete clustering tree.

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Full end‑to‑end MD workflow for 37 human protein–ATP holo structures..

## Simulation inventory

| # | Label | Protein | PDB | Case | Directory |
|---|-------|---------|-----|------|-----------|
| 1 | o15197_ATP | EPHB6 | o15197.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP` |
| 2 | o43187_ATP | IRAK2 | o43187.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP` |
| 3 | o60674_ATP | JAK2 | o60674.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP` |
| 4 | p00533_ATP | EGFR | p00533.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP` |
| 5 | p17612_ATP | KAPCA | p17612.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP` |
| 6 | p21860_ATP | ERBB3 | p21860.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP` |
| 7 | p23458_ATP | JAK1 | p23458.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP` |
| 8 | p24941_ATP | CDK2 | p24941.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP` |
| 9 | p25092_ATP | GUC2C | p25092.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP` |
| 10 | p28482_ATP | MK01 | p28482.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP` |
| 11 | p29597_ATP | TYK2 | p29597.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP` |
| 12 | p51841_ATP | GUC2F | p51841.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP` |
| 13 | p52333_ATP | JAK3 | p52333.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP` |
| 14 | q05823_ATP | RN5A | q05823.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP` |
| 15 | q13308_ATP | PTK7 | q13308.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP` |
| 16 | q13418_ATP | ILK | q13418.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP` |
| 17 | q58a45_ATP | PAN3 | q58a45.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP` |
| 18 | q5jzy3_ATP | EPHAA | q5jzy3.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP` |
| 19 | q6vab6_ATP | KSR2 | q6vab6.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP` |
| 20 | q7rtn6_ATP | STRAA | q7rtn6.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP` |
| 21 | q7z7a4_ATP | PXK | q7z7a4.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP` |
| 22 | q8iv63_ATP | VRK3 | q8iv63.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP` |
| 23 | q8ivt5_ATP | KSR1 | q8ivt5.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP` |
| 24 | q8nb16_ATP | MLKL | q8nb16.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP` |
| 25 | q8ncb2_ATP | CAMKV | q8ncb2.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP` |
| 26 | q8ne28_ATP | STKL1 | q8ne28.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP` |
| 27 | q8tea7_ATP | TBCK | q8tea7.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP` |
| 28 | q8wz42_ATP | TITIN | q8wz42.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP` |
| 29 | q92519_ATP | TRIB2 | q92519.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP` |
| 30 | q96c45_ATP | ULK4 | q96c45.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP` |
| 31 | q96qs6_ATP | PSKH2 | q96qs6.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP` |
| 32 | q9bxu1_ATP | STK31 | q9bxu1.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP` |
| 33 | q9c0k7_ATP | STRAB | q9c0k7.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP` |
| 34 | q9nsy0_ATP | NRBP2 | q9nsy0.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP` |
| 35 | q9uhy1_ATP | NRBP | q9uhy1.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP` |
| 36 | q9y243_ATP | AKT3 | q9y243.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP` |
| 37 | q9y616_ATP | IRAK3 | q9y616.pdb | Full end‑to‑end MD workflow for 37 human protein–ATP holo structures. | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP` |

## Pre-Combined Plan (before per-sim traj analysis)

Perform a cross‑simulation setup before per‑simulation analysis. First, build a global multiple‑sequence alignment of all 37 protein sequences using MAFFT, generating a consensus sequence and a residue‑mapping CSV. Next, define the ATP‑binding pocket of the reference KAPCA (p17612) by selecting residues within 15 Å of ATP, then map this pocket onto each protein using the alignment, producing pocket_mapped.json for every system. Store the consensus MSA, pocket mapping, and alignment JSON in the base/cross_sim/ directory for later use.

## Post-Combined Plan (after all per-sim analysis+reporter)

After all per‑simulation analyses are complete, aggregate the ten scalar descriptors from each system into a single feature table. Perform Ward hierarchical clustering on the z‑scaled features, generate a dendrogram and a heatmap of the scaled descriptors. Finally, produce a combined HTML report that includes the dendrogram, heatmap, literature context, and a brief interpretation marking a k=4 cut. All artifacts are written to the campaign root.