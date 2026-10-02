# AgenticAI Workflow Run Summary

**Generated:** 2026-09-22T18:40:33
**Mode:** multi_simulation
**Working directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02`

## Goal

I have 10 human protein–ATP holo structures in given working directory
(one PDB per system), spanning active kinases and pseudokinases.
Please run a full end-to-end comparative MD study on all of them.

Systems (UniProt id : protein name):
  p17612:KAPCA, o60674:JAK2, p24941:CDK2, q8ivt5:KSR1, q13418:ILK, p00533:EGFR,
  p23458:JAK1, q6vab6:KSR2, q92519:TRIB2, q9y243:AKT3

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
| Total simulations | 10 |
| Source PDBs | 10 |
| Succeeded | 10 |
| Skipped | 0 |
| Failed | 0 |

## Science completeness

| Metric | Value |
|--------|-------|
| Family modular | True |
| Systems with required artifacts | 10/10 |
| Feature matrix ready | True |
| Campaign science OK | True |

## Simulations

### o60674_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/o60674_ATP`

### p24941_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p24941_ATP`

### q8ivt5_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q8ivt5_ATP`

### q13418_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q13418_ATP`

### p00533_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p00533_ATP`

### p23458_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p23458_ATP`

### q6vab6_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q6vab6_ATP`

### q92519_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q92519_ATP`

### q9y243_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/q9y243_ATP`

### p17612_ATP — success
- **Directory:** `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/p17612_ATP`

## Artifacts

- Log: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/agent_conversation.log`
- Execution report: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/supervisor/execution_report.md`
- Reporter output: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/reporter/combined_report.html`

## LLM token usage

| Metric | Value |
|--------|-------|
| Calls | 65 |
| Prompt tokens | 158,749 |
| Completion tokens | 95,705 |
| Total tokens | 254,454 |

### By agent

- **analysis:** 9,722 tokens (1 calls)
- **final_report:** 67,904 tokens (20 calls)
- **planner:** 31,581 tokens (5 calls)
- **preprocess:** 21,441 tokens (4 calls)
- **reporter:** 12,470 tokens (3 calls)
- **simsetup:** 25,343 tokens (5 calls)
- **supervisor:** 98,165 tokens (29 calls)

Full usage log: `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_02/llm_usage.json`