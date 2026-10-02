# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single rich comparison HTML report that stitches together the analysis summaries and overlay plots from the five MD simulation runs.  We will therefore read the analysis_summary.jsonl files from each simulation directory, collect the overlay images that were produced during the combined analysis phase, and feed them to the `generate_combined_html_report` tool.  No additional analysis or literature searching is required because the framework already handles literature retrieval internally.  The report will be written in the reporter output directory, using the default name `combined_report.html` and a concise title that reflects the comparative study of pseudokinases and kinases.

## Overview

A comprehensive, self‑contained HTML report that aggregates quantitative descriptors, clustering dendrograms, MSA visualisations, and key literature for the five ATP‑bound kinase / pseudokinase structures.  The report highlights similarities and differences in ATP binding, pocket dynamics, flexibility, and inter‑lobe communication across the systems.

## Report Focus

- MD Simulation Comparison
- Pseudokinase Dynamics

## Execution Steps (3 steps)

### Step 1: Collect simulation directories and labels

**Tool:** `none`

**Description:** Define the absolute paths of the five simulation root directories and assign human‑readable labels for each.

**Reason:** The report generator requires the list of simulation roots and a readable name for each dataset.

**Parameters:**
```json
{
  "sim_dirs": [
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p17612_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/o60674_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p24941_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/q8ivt5_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/q13418_ATP"
  ],
  "labels": [
    "p17612_ATP",
    "o60674_ATP",
    "p24941_ATP",
    "q8ivt5_ATP",
    "q13418_ATP"
  ]
}
```

### Step 2: Gather overlay plot paths

**Tool:** `none`

**Description:** Specify the PNG/JPEG files that were produced by the combined analysis (MSA, clustering, pocket metrics, DCCM, etc.).  These images are located in the analysis directory.

**Reason:** These visualisations provide the key comparative insights that the report will embed.

**Parameters:**
```json
{
  "overlay_plots": [
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/sequence_phylo_tree.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/classification_clusters_pca.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/classification_dendrogram_heatmap.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/classification_phylo_tree.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_com_distance_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_hbonds_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_sasa_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_ligand_residence_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_ligand_axis_angle_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_rmsf_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/dccm_comparison.png"
  ]
}
```

### Step 3: Generate combined HTML report

**Tool:** `generate_combined_html_report`

**Description:** Invoke the report generator with the collected parameters to produce a self‑contained HTML file in the reporter output directory.

**Reason:** This is the mandatory step that produces the final HTML report in the reporter directory.

**Parameters:**
```json
{
  "sim_dirs": [
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p17612_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/o60674_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/p24941_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/q8ivt5_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/q13418_ATP"
  ],
  "labels": [
    "p17612_ATP",
    "o60674_ATP",
    "p24941_ATP",
    "q8ivt5_ATP",
    "q13418_ATP"
  ],
  "overlay_plots": [
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/sequence_phylo_tree.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/classification_clusters_pca.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/classification_dendrogram_heatmap.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/classification_phylo_tree.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_com_distance_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_hbonds_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_sasa_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_ligand_residence_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_ligand_axis_angle_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/ref_fel_pock_rmsf_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_01/analysis/dccm_comparison.png"
  ],
  "working_dir": ".",
  "output_file": "combined_report.html",
  "title": "Comparative Dynamics of ATP\u2011Bound Kinase / Pseudokinase Systems",
  "enriched_prompt": "Original study goal: comparative MD analysis of ATP\u2011bound kinase and pseudokinase structures to extract consensus pocket dynamics, flexibility, inter\u2011lobe communication and dihedral PCA metrics.",
  "user_goal": "Perform a full end\u2011to\u2011end comparative MD study on 5 ATP holo kinase / pseudokinase structures, compute ten scalar descriptors, cluster the systems, and produce a comprehensive report.",
  "protein_name": "ATP\u2011bound Kinase/Pseudokinase Ensemble"
}
```

