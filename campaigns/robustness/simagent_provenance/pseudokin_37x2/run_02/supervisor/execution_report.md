# MD Workflow Execution Report

**Generated:** 2026-09-24 00:45:35  
**Status:** IN PROGRESS (analysis)

---

## User Prompt

> ## Original Study Goal

I have 37 human protein–ATP holo structures in given working directory
(one PDB per system). There are 32 pseudokinases and 5 ground-truth active kinases.
Please run a full end-to-end comparative MD study on all of them.

Systems (UniProt id : protein name):
  o15197:EPHB6, o43187:IRAK2, o60674:JAK2, p00533:EGFR, p17612:KAPCA, p21860:ERBB3, p23458:JAK1, p24941:CDK2, p25092:GUC2C, p28482:MK01, p29597:TYK2, p51841:GUC2F, p52333:JAK3,
  q05823:RN5A, q13308:PTK7, q13418:ILK, q58a45:PAN3, q5jzy3:EPHAA, q6vab6:KSR2, q7rtn6:STRAA, q7z7a4:PXK, q8iv63:VRK3, q8ivt5:KSR1, q8nb16:MLKL, q8ncb2:CAMKV, q8ne28:STKL1,
  q8tea7:TBCK, q8wz42:TITIN, q92519:TRIB2, q96c45:ULK4, q96qs6:PSKH2, q9bxu1:STK31, q9c0k7:STRAB, q9nsy0:NRBP2, q9uhy1:NRBP, q9y243:AKT3, q9y616:IRAK3

For each complex, preprocess the structure and set up GROMACS with
AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, and 0.15 M NaCl.
Run two independent 200 ns production MD replicates per system, wait for all
simulations to finish, then analyze and plot the full 200 ns of every
trajectory (do not truncate to a shorter window).

Use KAPCA (p17612) as the reference to define the ATP-binding pocket
(residues within 15 Å of ATP, unless a different cutoff is stated), map that
pocket onto the other proteins with a global sequence alignment
(MAFFT / star MSA), and plot both the global MSA and the pocket /
high-consensus MSA panels.

From both replicates (then average across replicates), extract these ten
scalar dynamics descriptors for every system. All ten are required for
clustering — do not drop any:

1. ATP COM distance to the consensus pocket — mean
2. ATP COM distance to the consensus pocket — standard deviation
3. ATP orientation vs the pocket axis — mean axis angle
4. ATP orientation vs the pocket axis — standard deviation of the axis angle
5. Pocket side-chain χ₁ circular mean
6. Pocket side-chain χ₁ circular standard deviation
7. Flexibility of consensus-mapped Cα atoms — mean RMSF
8. Flexibility of consensus-mapped Cα atoms — standard deviation of RMSF
9. N-lobe ↔ C-lobe DCCM mean correlation
10. Shared-reference φ/ψ/χ₁ dihedral PCA dynamics scalar
    (pca_pka_ref_shared_dyn = √(d_g² + d_c² + pc_rms²) vs KAPCA in the
     shared PKA PC space; do not substitute independent per-protein PCA
     grid entropy)

When all systems are done, assemble those ten descriptors into one feature
table, run Ward hierarchical clustering, and write a single dendrogram +
feature-heatmap panel (robust z-score / IQR scaling). Also write a combined
HTML report with brief literature context. You may mark a k=4 cut for
interpretation, but still emit the full tree.

## Combined Multi-Simulation Analysis (post)

After all per‑simulation analyses are complete, aggregate the ten scalar descriptors from each system into a single feature table. Perform Ward hierarchical clustering on the z‑scaled features, generate a dendrogram and a heatmap of the scaled descriptors. Finally, produce a combined HTML report that includes the dendrogram, heatmap, literature context, and a brief interpretation marking a k=4 cut. All artifacts are written to the campaign root.

## Simulation Data

### Simulation: o15197_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: o43187_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: o60674_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p00533_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p17612_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p21860_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p23458_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p24941_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p25092_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p28482_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p29597_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p51841_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p52333_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q05823_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q13308_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q13418_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q58a45_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q5jzy3_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q6vab6_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q7rtn6_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q7z7a4_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8iv63_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8ivt5_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8nb16_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8ncb2_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8ne28_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8tea7_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8wz42_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q92519_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q96c45_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q96qs6_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9bxu1_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9c0k7_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9nsy0_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9uhy1_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9y243_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9y616_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1


Save all combined plots and reports to the analysis and reporter directories under: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02

## Enriched Prompt

## Original Study Goal

I have 37 human protein–ATP holo structures in given working directory
(one PDB per system). There are 32 pseudokinases and 5 ground-truth active kinases.
Please run a full end-to-end comparative MD study on all of them.

Systems (UniProt id : protein name):
  o15197:EPHB6, o43187:IRAK2, o60674:JAK2, p00533:EGFR, p17612:KAPCA, p21860:ERBB3, p23458:JAK1, p24941:CDK2, p25092:GUC2C, p28482:MK01, p29597:TYK2, p51841:GUC2F, p52333:JAK3,
  q05823:RN5A, q13308:PTK7, q13418:ILK, q58a45:PAN3, q5jzy3:EPHAA, q6vab6:KSR2, q7rtn6:STRAA, q7z7a4:PXK, q8iv63:VRK3, q8ivt5:KSR1, q8nb16:MLKL, q8ncb2:CAMKV, q8ne28:STKL1,
  q8tea7:TBCK, q8wz42:TITIN, q92519:TRIB2, q96c45:ULK4, q96qs6:PSKH2, q9bxu1:STK31, q9c0k7:STRAB, q9nsy0:NRBP2, q9uhy1:NRBP, q9y243:AKT3, q9y616:IRAK3

For each complex, preprocess the structure and set up GROMACS with
AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, and 0.15 M NaCl.
Run two independent 200 ns production MD replicates per system, wait for all
simulations to finish, then analyze and plot the full 200 ns of every
trajectory (do not truncate to a shorter window).

Use KAPCA (p17612) as the reference to define the ATP-binding pocket
(residues within 15 Å of ATP, unless a different cutoff is stated), map that
pocket onto the other proteins with a global sequence alignment
(MAFFT / star MSA), and plot both the global MSA and the pocket /
high-consensus MSA panels.

From both replicates (then average across replicates), extract these ten
scalar dynamics descriptors for every system. All ten are required for
clustering — do not drop any:

1. ATP COM distance to the consensus pocket — mean
2. ATP COM distance to the consensus pocket — standard deviation
3. ATP orientation vs the pocket axis — mean axis angle
4. ATP orientation vs the pocket axis — standard deviation of the axis angle
5. Pocket side-chain χ₁ circular mean
6. Pocket side-chain χ₁ circular standard deviation
7. Flexibility of consensus-mapped Cα atoms — mean RMSF
8. Flexibility of consensus-mapped Cα atoms — standard deviation of RMSF
9. N-lobe ↔ C-lobe DCCM mean correlation
10. Shared-reference φ/ψ/χ₁ dihedral PCA dynamics scalar
    (pca_pka_ref_shared_dyn = √(d_g² + d_c² + pc_rms²) vs KAPCA in the
     shared PKA PC space; do not substitute independent per-protein PCA
     grid entropy)

When all systems are done, assemble those ten descriptors into one feature
table, run Ward hierarchical clustering, and write a single dendrogram +
feature-heatmap panel (robust z-score / IQR scaling). Also write a combined
HTML report with brief literature context. You may mark a k=4 cut for
interpretation, but still emit the full tree.

## Combined Multi-Simulation Analysis (post)

After all per‑simulation analyses are complete, aggregate the ten scalar descriptors from each system into a single feature table. Perform Ward hierarchical clustering on the z‑scaled features, generate a dendrogram and a heatmap of the scaled descriptors. Finally, produce a combined HTML report that includes the dendrogram, heatmap, literature context, and a brief interpretation marking a k=4 cut. All artifacts are written to the campaign root.

## Simulation Data

### Simulation: o15197_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: o43187_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: o60674_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p00533_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p17612_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p21860_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p23458_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p24941_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p25092_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p28482_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p29597_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p51841_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: p52333_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q05823_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q13308_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q13418_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q58a45_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q5jzy3_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q6vab6_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q7rtn6_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q7z7a4_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8iv63_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8ivt5_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8nb16_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8ncb2_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8ne28_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8tea7_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q8wz42_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q92519_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q96c45_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q96qs6_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9bxu1_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9c0k7_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9nsy0_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9uhy1_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9y243_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1

### Simulation: q9y616_ATP
- Working directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP
- Analysis directory: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP/analysis
- Analysis summary: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP/analysis/analysis_summary.jsonl
- Trajectory: None
- Topology: None
- Energy: None
- Figures generated: 0
- Errors: 1


Save all combined plots and reports to the analysis and reporter directories under: /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02

## Execution Plan

**Combined Multi-Simulation Analysis**

Agent sequence: analysis → reporter

## Original Study Goal

I have 37 human protein–ATP holo structures in given working directory
(one PDB per system). There are 32 pseudokinases and 5 ground-truth active kinases.
Please run a full end-to-end comparative MD study on all of them.

Systems (UniProt id : protein name):
  o15197:EPHB6, o43187:IRAK2, o60674:JAK2, p00533:EGFR, p17612:KAPCA, p21860:ERBB3, p23458:JAK1, p24941:CDK2, p25092:GUC2C, p28482:MK01, p29597:TYK2, p51841:GUC2F, p52333:JAK3,
  q05823:RN5A, q13308:PTK7, q13418:ILK, q58a45:PAN3, q5jzy3:EPHAA, q6vab6:KSR2, q7rtn6:STRAA, q7z7a4:PXK, q8iv63:VRK3, q8ivt5:KSR1, q8nb16:MLKL, q8ncb2:CAMKV, q8ne28:STKL1,
  q8tea7:TBCK, q8wz42:TITIN, q92519:TRIB2, q96c45:ULK4, q96qs6:PSKH2, q9bxu1:STK31, q9c0k7:STRAB, q9nsy0:NRBP2, q9uhy1:NRBP, q9y243:AKT3, q9y616:IRAK3

For each complex, preprocess the structure and set up GROMACS with
AMBER99SB-ILDN, TIP3P water, 310 K, 1 bar, and 0.15 M NaCl.
Run two independent 200 ns production MD replicates per system, wait for all
simulations to finish, then analyze and plot the full 200 ns of every
trajectory (do not truncate to a shorter window).

Use KAPCA (p17612) as the reference to define the ATP-binding pocket
(residues within 15 Å of ATP, unless a different cutoff is stated), map that
pocket onto the other proteins with a global sequence alignment
(MAFFT / star MSA), and plot both the global MSA and the pocket /
high-consensus MSA panels.

From both replicates (then average across replicates), extract these ten
scalar dynamics descriptors for every system. All ten are required for
clustering — do not drop any:

1. ATP COM distance to the consensus pocket — mean
2. ATP COM distance to the consensus pocket — standard deviation
3. ATP orientation vs the pocket axis — mean axis angle
4. ATP orientation vs the pocket axis — standard deviation of the axis angle
5. Pocket side-chain χ₁ circular mean
6. Pocket side-chain χ₁ circular standard deviation
7. Flexibility of consensus-mapped Cα atoms — mean RMSF
8. Flexibility of consensus-mapped Cα atoms — standard deviation of RMSF
9. N-lobe ↔ C-lobe DCCM mean correlation
10. Shared-reference φ/ψ/χ₁ dihedral PCA dynamics scalar
    (pca_pka_ref_shared_dyn = √(d_g² + d_c² + pc_rms²) vs KAPCA in the
     shared PKA PC space; do not substitute independent per-protein PCA
     grid entropy)

When all systems are done, assemble those ten descriptors into one feature
table, run Ward hierarchical clustering, and write a single dendrogram +
feature-heatmap panel (robust z-score / IQR scaling). Also write a combined
HTML report with brief literature context. You may mark a k=4 cut for
interpretation, but still emit the full tree.

## Combined Multi-Simulation Analysis (post)

After all per‑simulation analyses are complete, aggregate the ten scalar descriptors from each system into a single feature table. Perform Ward hierarchical clustering on the z‑scaled features, generate a dendrogram and a heatmap of the scaled descriptors. Finally, produce a combined HTML repor...

## Key Artifacts

- Figures: 11 generated

## Summary

Workflow in progress — last completed stage: **analysis**
