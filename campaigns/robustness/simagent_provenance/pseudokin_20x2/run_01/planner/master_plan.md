# Multi-Simulation Master Plan

**Generated:** 2026-09-23 12:27:51
**Simulations:** 20
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** yes
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

Preprocess the 20 holo PDBs by extracting only the protein, ligand (ATP) and ion (Mg²⁺) components, discarding any water, and prepare cleaned coordinate files.  
Set up GROMACS for each system using amber99sb‑ildn, TIP3P, 310 K, 1 bar, 0.15 M NaCl, a cubic box with 1.2 nm buffer, generating the necessary topology, coordinates, MDP, and TPR files.  
Submit and run two independent 200 ns production MD replicates per system on the HPC, ensuring all trajectories are completed before proceeding.  
Analyze each full 200 ns trajectory to (i) map the ATP‑binding pocket from KAPCA (p17612) onto the other proteins via MAFFT MSA, (ii) compute the ten scalar dynamics descriptors (ATP COM distance/angle, pocket χ₁ mean & SD, Cα RMSF mean & SD, DCCM mean correlation, shared‑reference PCA scalar) for both replicates and average them, (iii) assemble the descriptors into a feature table, and (iv) perform Ward hierarchical clustering, generating a dendrogram and feature‑heatmap (robust z‑score/IQR scaling) while noting a k = 4 cut but retaining the full tree.  
Produce a single HTML report that includes the dendrogram, heatmap, the compiled feature table, and brief literature context for the kinases/pseudokinases.

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Protein–ATP holo.

## Simulation inventory

| # | Label | Protein | PDB | Case | Directory |
|---|-------|---------|-----|------|-----------|
| 1 | p17612_ATP | KAPCA | p17612.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p17612_ATP` |
| 2 | o60674_ATP | JAK2 | o60674.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o60674_ATP` |
| 3 | p24941_ATP | CDK2 | p24941.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p24941_ATP` |
| 4 | q8ivt5_ATP | KSR1 | q8ivt5.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q8ivt5_ATP` |
| 5 | q13418_ATP | ILK | q13418.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q13418_ATP` |
| 6 | p00533_ATP | EGFR | p00533.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p00533_ATP` |
| 7 | p23458_ATP | JAK1 | p23458.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p23458_ATP` |
| 8 | q6vab6_ATP | KSR2 | q6vab6.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q6vab6_ATP` |
| 9 | q92519_ATP | TRIB2 | q92519.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q92519_ATP` |
| 10 | q9y243_ATP | AKT3 | q9y243.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q9y243_ATP` |
| 11 | o15197_ATP | EPHB6 | o15197.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o15197_ATP` |
| 12 | o43187_ATP | IRAK2 | o43187.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o43187_ATP` |
| 13 | p21860_ATP | ERBB3 | p21860.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p21860_ATP` |
| 14 | p25092_ATP | GUC2C | p25092.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p25092_ATP` |
| 15 | p28482_ATP | MK01 | p28482.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p28482_ATP` |
| 16 | p29597_ATP | TYK2 | p29597.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p29597_ATP` |
| 17 | p51841_ATP | GUC2F | p51841.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p51841_ATP` |
| 18 | p52333_ATP | JAK3 | p52333.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p52333_ATP` |
| 19 | q05823_ATP | RN5A | q05823.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q05823_ATP` |
| 20 | q13308_ATP | PTK7 | q13308.pdb | Protein–ATP holo | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q13308_ATP` |

## Pre-Combined Plan (before per-sim traj analysis)

Before per‑simulation analysis, perform cross‑simulation preprocessing: 1) Build a global MAFFT MSA of all 20 holo kinase sequences using KAPCA (p17612) as reference. 2) Identify the ATP‑binding pocket in KAPCA (residues within 15 Å of ATP). 3) Map that pocket onto each protein via the consensus alignment to obtain pocket residue lists per system. 4) Store the consensus pocket mapping and alignment JSON in base/cross_sim/ for downstream analysis.

## Post-Combined Plan (after all per-sim analysis+reporter)

After all per‑simulation analysis and reporter steps complete, aggregate the ten scalar descriptors from each system, compute a Ward hierarchical clustering, generate a dendrogram and robust z‑score/IQR‑scaled heatmap, and produce a combined HTML report with the dendrogram, heatmap, feature table, and literature context. The report will also highlight a k=4 cut for interpretation but retain the full tree.