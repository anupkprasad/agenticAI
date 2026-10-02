# Multi-Simulation Master Plan

**Generated:** 2026-09-23 14:26:08
**Simulations:** 20
**Pipeline:** preprocess -> simsetup -> hpcjob -> analysis -> reporter
**Task scope:** full_pipeline
**Pre-combined (before traj):** yes
**Post-combined (after all sims):** yes
**Combined analysis requested (legacy=post):** yes

## Overall Goal

**Rephrased Goal (workflow‑scope compliant)**  

1. **Preprocessing:** For each of the 20 PDB files, keep only the protein, ATP ligand, and ions; remove all water. Add any missing atoms and generate a clean coordinate file for each system.  
2. **Simulation Setup:** Create GROMACS input files (topology, coordinates, MDP, TPR) for two independent 200‑ns production runs per system using amber99sb‑ildn, TIP3P water, 310 K, 1 bar, 0.15 M NaCl, cubic box with a 1.2 nm buffer.  
3. **HPC Execution:** Submit and monitor the 40 trajectories, ensuring all simulations finish.  
4. **Analysis:** (i) Identify the ATP‑binding pocket in KAPCA (residues within 15 Å of ATP), map this pocket to the other proteins via MAFFT alignment, and plot both the global MSA and the pocket‑specific MSA. (ii) For each system, compute the ten required scalar descriptors across the two replicas and average them: ATP COM distance (mean, SD), ATP orientation angle (mean, SD), pocket χ₁ mean/SD, Cα RMSF mean/SD, N‑lobe ↔ C‑lobe DCCM mean, shared‑reference dihedral PCA metric. (iii) Assemble the descriptors into a feature table, perform Ward hierarchical clustering, and generate a dendrogram + feature‑heatmap (robust z‑score/IQR scaling).  
5. **Reporter:** Produce a single HTML report that includes the feature table, clustering results, dendrogram, heatmap, and a concise literature context, marking a k = 4 cut for interpretation while retaining the full tree.

## Shared per-simulation intent

For each simulation label below, run the same pipeline (preprocess -> simsetup -> hpcjob -> analysis -> reporter) using that label's PDB / working directory and case directive. Cases in this campaign: Protein–ATP holo complex.

## Simulation inventory

| # | Label | Protein | PDB | Case | Directory |
|---|-------|---------|-----|------|-----------|
| 1 | p17612_ATP | KAPCA | p17612.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p17612_ATP` |
| 2 | o60674_ATP | JAK2 | o60674.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/o60674_ATP` |
| 3 | p24941_ATP | CDK2 | p24941.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p24941_ATP` |
| 4 | q8ivt5_ATP | KSR1 | q8ivt5.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q8ivt5_ATP` |
| 5 | q13418_ATP | ILK | q13418.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q13418_ATP` |
| 6 | p00533_ATP | EGFR | p00533.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p00533_ATP` |
| 7 | p23458_ATP | JAK1 | p23458.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p23458_ATP` |
| 8 | q6vab6_ATP | KSR2 | q6vab6.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q6vab6_ATP` |
| 9 | q92519_ATP | TRIB2 | q92519.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q92519_ATP` |
| 10 | q9y243_ATP | AKT3 | q9y243.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q9y243_ATP` |
| 11 | o15197_ATP | EPHB6 | o15197.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/o15197_ATP` |
| 12 | o43187_ATP | IRAK2 | o43187.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/o43187_ATP` |
| 13 | p21860_ATP | ERBB3 | p21860.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p21860_ATP` |
| 14 | p25092_ATP | GUC2C | p25092.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p25092_ATP` |
| 15 | p28482_ATP | MK01 | p28482.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p28482_ATP` |
| 16 | p29597_ATP | TYK2 | p29597.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p29597_ATP` |
| 17 | p51841_ATP | GUC2F | p51841.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p51841_ATP` |
| 18 | p52333_ATP | JAK3 | p52333.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/p52333_ATP` |
| 19 | q05823_ATP | RN5A | q05823.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q05823_ATP` |
| 20 | q13308_ATP | PTK7 | q13308.pdb | Protein–ATP holo complex | `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_02/q13308_ATP` |

## Pre-Combined Plan (before per-sim traj analysis)

Before any per‑simulation analysis, perform the shared cross‑simulation setup in the base/cross_sim/ directory:
1. Use the KAPCA (p17612) holo structure as the reference. Identify the ATP‑binding pocket as all residues within 15 Å of the ATP ligand.
2. Export this pocket residue list and map it onto each of the 19 other proteins via a global MAFFT alignment (build_consensus_sequence_alignment, build_global_mapped_alignment). Store the resulting alignment JSON and consensus residue mapping files.
3. Generate a pocket‑specific MSA by filtering the global alignment to the mapped pocket residues (build_sequence_phylo_tree or a custom filter). Save the pocket MSA and the global MSA.
4. Produce visualizations of the global MSA and pocket MSA (e.g., using plot_msa). 
5. Store all artifacts (pocket_mapped.json, global_mapped.json, alignment.json, MSA files) in base/cross_sim/ for downstream per‑simulation analysis.
This step ensures every simulation has a consistent reference pocket and sequence mapping for the ten scalar descriptors.

## Post-Combined Plan (after all per-sim analysis+reporter)

After all per‑simulation analyses and reporters finish, aggregate the ten‑descriptor tables from each system:
1. Collect the per‑simulation CSV files (one per system) into a single feature table using collect_metric_files and compute_comparison_table.
2. Apply robust z‑score/IQR scaling to each feature column.
3. Perform Ward hierarchical clustering (cluster_classification_features) on the scaled table, requesting a dendrogram and heatmap. Generate a dendrogram plot and a feature‑heatmap panel.
4. Mark a k=4 cut on the dendrogram for interpretation but retain the full tree.
5. Compile the clustering results, dendrogram, heatmap, and the individual per‑system plots into a single combined HTML report using generate_combined_html_report, adding concise literature context for each protein family.
6. Output the final report to the campaign root and archive the feature table and clustering artifacts.