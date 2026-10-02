# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already performed all simulations and generated a comprehensive set of analysis plots and a per‑simulation analysis_summary.jsonl file. The only remaining task for the Reporter Agent is to collate these results into a single, self‑contained HTML report that showcases the clustering, phylogenetic, and functional comparisons across all 37 protein‑ATP complexes.  We will use the dedicated `generate_combined_html_report` tool, which automatically reads each analysis_summary.jsonl, embeds all overlay plots, and gathers literature references.  Because the analysis files and plots already exist in the analysis directory, no additional data processing steps are required beyond invoking this tool with the correct parameters.

## Overview

A comprehensive, web‑ready report that presents the full hierarchy of clustering and phylogenetic relationships, visualizes key kinetic and structural metrics, and embeds literature context for the 37 pseudokinase and active kinase systems studied in this campaign.

## Report Focus

- MD Dynamics
- Pseudokinase Function

## Execution Steps (1 steps)

### Step 1: Generate Combined HTML Report

**Tool:** `generate_combined_html_report`

**Description:** Create a single HTML document that combines per‑simulation analysis summaries, overlay plots, and literature references for all 37 protein‑ATP complexes.

**Reason:** The report must be generated in a single step using the dedicated combined report generator, as all analysis data and plots are already available.

**Parameters:**
```json
{
  "sim_dirs": [
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o15197_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o43187_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/o60674_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p00533_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p17612_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p21860_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p23458_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p24941_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p25092_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p28482_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p29597_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p51841_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/p52333_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q05823_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13308_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q13418_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q58a45_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q5jzy3_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q6vab6_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7rtn6_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q7z7a4_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8iv63_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ivt5_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8nb16_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ncb2_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8ne28_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8tea7_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q8wz42_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q92519_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96c45_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q96qs6_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9bxu1_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9c0k7_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9nsy0_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9uhy1_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y243_ATP",
    "/home/akp66103/space/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_02/q9y616_ATP"
  ],
  "labels": [
    "EPHB6",
    "IRAK2",
    "JAK2",
    "EGFR",
    "KAPCA",
    "ERBB3",
    "JAK1",
    "CDK2",
    "GUC2C",
    "MK01",
    "TYK2",
    "GUC2F",
    "JAK3",
    "RN5A",
    "PTK7",
    "ILK",
    "PAN3",
    "EPHAA",
    "KSR2",
    "STRAA",
    "PXK",
    "VRK3",
    "KSR1",
    "MLKL",
    "CAMKV",
    "STKL1",
    "TBCK",
    "TITIN",
    "TRIB2",
    "ULK4",
    "PSKH2",
    "STK31",
    "STRAB",
    "NRBP2",
    "NRBP",
    "AKT3",
    "IRAK3"
  ],
  "overlay_plots": [
    "sequence_phylo_tree.png",
    "classification_clusters_pca.png",
    "classification_dendrogram_heatmap.png",
    "classification_phylo_tree.png",
    "ref_fel_pock_com_distance_by_cluster.png",
    "ref_fel_pock_hbonds_by_cluster.png",
    "ref_fel_pock_sasa_by_cluster.png",
    "ref_fel_pock_ligand_residence_by_cluster.png",
    "ref_fel_pock_ligand_axis_angle_by_cluster.png",
    "ref_fel_pock_rmsf_by_cluster.png",
    "dccm_comparison.png"
  ],
  "working_dir": ".",
  "output_file": "combined_report.html",
  "title": "Combined MD Analysis of 37 Pseudokinase and Active Kinase Systems",
  "enriched_prompt": "I am the Reporter Agent in COMBINED multi-simulation mode. Original study goal: I have 37 human protein\u2013ATP holo structures in given working directory (one PDB per system). There are 32 pseudokinases and 5 ground-truth active kinases. Please run a full end-to-end comparative MD study on all of them. ...",
  "user_goal": "I have 37 human protein\u2013ATP holo structures in given working directory (one PDB per system). There are 32 pseudokinases and 5 ground-truth active kinases. Please run a full end-to-end comparative MD study on all of them."
}
```

