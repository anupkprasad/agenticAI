# AgenticAI Workflow Run Summary

**Generated:** 2026-09-23T21:18:35
**Mode:** multi_simulation
**Working directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01`

## Goal

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

## Counts

| Metric | Value |
|--------|-------|
| Total simulations | 37 |
| Source PDBs | 37 |
| Succeeded | 36 |
| Skipped | 0 |
| Failed | 1 |

## Science completeness

| Metric | Value |
|--------|-------|
| Family modular | True |
| Systems with required artifacts | 37/37 |
| Feature matrix ready | True |
| Campaign science OK | True |

## Simulations

### o43187_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o43187_ATP`

### o60674_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o60674_ATP`

### p00533_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p00533_ATP`

### p17612_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p17612_ATP`

### p21860_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p21860_ATP`

### p23458_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p23458_ATP`

### p24941_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p24941_ATP`

### p25092_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p25092_ATP`

### p28482_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p28482_ATP`

### p29597_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p29597_ATP`

### p51841_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p51841_ATP`

### p52333_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p52333_ATP`

### q05823_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q05823_ATP`

### q13308_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13308_ATP`

### q13418_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13418_ATP`

### q58a45_ATP — failed
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q58a45_ATP`
- **Errors:**
  - Analysis failed after 3 retries

### q5jzy3_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q5jzy3_ATP`

### q6vab6_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q6vab6_ATP`

### q7rtn6_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7rtn6_ATP`

### q7z7a4_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7z7a4_ATP`

### q8iv63_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8iv63_ATP`

### q8ivt5_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ivt5_ATP`

### q8nb16_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8nb16_ATP`

### q8ncb2_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ncb2_ATP`

### q8ne28_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ne28_ATP`

### q8tea7_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8tea7_ATP`

### q8wz42_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8wz42_ATP`

### q92519_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q92519_ATP`

### q96c45_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q96c45_ATP`

### q96qs6_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q96qs6_ATP`

### q9bxu1_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9bxu1_ATP`

### q9c0k7_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9c0k7_ATP`

### q9nsy0_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9nsy0_ATP`

### q9uhy1_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9uhy1_ATP`

### q9y243_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9y243_ATP`

### q9y616_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q9y616_ATP`

### o15197_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o15197_ATP`

## Artifacts

- Log: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/agent_conversation.log`
- Execution report: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/supervisor/execution_report.md`
- Reporter output: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/reporter/combined_report.html`

## LLM token usage

| Metric | Value |
|--------|-------|
| Calls | 239 |
| Prompt tokens | 619,681 |
| Completion tokens | 361,598 |
| Total tokens | 981,279 |

### By agent

- **analysis:** 15,634 tokens (1 calls)
- **final_report:** 271,100 tokens (73 calls)
- **planner:** 144,637 tokens (20 calls)
- **preprocess:** 79,631 tokens (15 calls)
- **reporter:** 12,275 tokens (3 calls)
- **simsetup:** 53,375 tokens (11 calls)
- **supervisor:** 423,054 tokens (118 calls)

Full usage log: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/llm_usage.json`