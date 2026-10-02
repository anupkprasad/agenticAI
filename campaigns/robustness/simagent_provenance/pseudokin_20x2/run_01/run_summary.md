# AgenticAI Workflow Run Summary

**Generated:** 2026-09-23T14:24:32
**Mode:** multi_simulation
**Working directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01`

## Goal

I have 20 human protein–ATP holo structures in given working directory
(one PDB per system), spanning active kinases and pseudokinases.
Please run a full end-to-end comparative MD study on all of them.

Systems (UniProt id : protein name):
  p17612:KAPCA, o60674:JAK2, p24941:CDK2, q8ivt5:KSR1, q13418:ILK, p00533:EGFR,
  p23458:JAK1, q6vab6:KSR2, q92519:TRIB2, q9y243:AKT3, o15197:EPHB6, o43187:IRAK2,
  p21860:ERBB3, p25092:GUC2C, p28482:MK01, p29597:TYK2, p51841:GUC2F, p52333:JAK3,
  q05823:RN5A, q13308:PTK7

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
| Total simulations | 20 |
| Source PDBs | 20 |
| Succeeded | 20 |
| Skipped | 0 |
| Failed | 0 |

## Science completeness

| Metric | Value |
|--------|-------|
| Family modular | True |
| Systems with required artifacts | 20/20 |
| Feature matrix ready | True |
| Campaign science OK | True |

## Simulations

### o60674_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o60674_ATP`

### p24941_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p24941_ATP`

### q8ivt5_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q8ivt5_ATP`

### q13418_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q13418_ATP`

### p00533_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p00533_ATP`

### p23458_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p23458_ATP`

### q6vab6_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q6vab6_ATP`

### q92519_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q92519_ATP`

### q9y243_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q9y243_ATP`

### o15197_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o15197_ATP`

### o43187_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/o43187_ATP`

### p21860_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p21860_ATP`

### p25092_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p25092_ATP`

### p28482_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p28482_ATP`

### p29597_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p29597_ATP`

### p51841_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p51841_ATP`

### p52333_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p52333_ATP`

### q05823_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q05823_ATP`

### q13308_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q13308_ATP`

### p17612_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/p17612_ATP`

## Artifacts

- Log: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/agent_conversation.log`
- Execution report: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/supervisor/execution_report.md`
- Reporter output: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/reporter/combined_report.html`

## LLM token usage

| Metric | Value |
|--------|-------|
| Calls | 132 |
| Prompt tokens | 274,729 |
| Completion tokens | 176,814 |
| Total tokens | 451,543 |

### By agent

- **analysis:** 11,178 tokens (1 calls)
- **final_report:** 112,146 tokens (40 calls)
- **planner:** 51,362 tokens (9 calls)
- **preprocess:** 43,429 tokens (8 calls)
- **reporter:** 22,857 tokens (6 calls)
- **simsetup:** 42,676 tokens (9 calls)
- **supervisor:** 179,073 tokens (60 calls)

Full usage log: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/llm_usage.json`