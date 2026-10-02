# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The combined report must aggregate all analysis results from the 37 MD simulations and embed the overlay plots that were generated during the analysis phase. The task requires only the `generate_combined_html_report` tool, as per the rules. Therefore the plan is: (1) build lists of simulation directories and human‑readable labels matching the folder names; (2) collect the absolute paths of all overlay plots that exist in the shared analysis directory; (3) invoke `generate_combined_html_report` with the required arguments, setting `working_dir` to the reporter output directory (which is automatically handled as `.`) and `output_file` to `combined_report.html`. No additional literature queries or clustering discussion are added because the corresponding plots are already available and the rules forbid fabricating new content.

## Overview

A single, self‑contained HTML report summarizing the 200‑ns MD trajectories of 37 human protein–ATP holo structures. The report consolidates scalar descriptors, hierarchical clustering heatmaps, phylogenetic trees, and ligand‑binding pocket analyses, and contextualises the findings with literature references.

## Report Focus

- Comprehensive MD Descriptor Comparison
- Ligand‑Binding Pocket Variability Across Kinase Family

## Execution Steps (3 steps)

### Step 1: Prepare simulation directories and labels

**Tool:** `none`

**Description:** Create ordered lists of the 37 simulation root directories and corresponding human‑readable labels.

**Reason:** These lists are required inputs for the report generator.

**Parameters:**
```json
{}
```

### Step 2: Collect overlay plot paths

**Tool:** `none`

**Description:** Generate absolute file paths for all overlay PNG/JPEG plots located in the analysis directory.

**Reason:** The report generator expects a list of overlay plot paths to embed in the final HTML.

**Parameters:**
```json
{}
```

### Step 3: Generate combined HTML report

**Tool:** `generate_combined_html_report`

**Description:** Invoke `generate_combined_html_report` with the simulation directories, labels, overlay plots, and other meta‑information such as title, enriched prompt, and user goal.

**Reason:** This is the single required tool call that produces the final combined HTML report.

**Parameters:**
```json
{
  "sim_dirs": [
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o15197_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o43187_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/o60674_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p00533_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p17612_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p21860_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p23458_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p24941_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p25092_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p28482_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p29597_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p51841_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/p52333_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q05823_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13308_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q13418_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q58a45_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q5jzy3_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q6vab6_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7rtn6_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q7z7a4_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8iv63_ATP",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q8ivt5_ATP",
    "/home/akp6613.../q8nb16_ATP",
    "/home/akp66103/.../q8ncb2_ATP",
    "/home/akp66103/.../q8ne28_ATP",
    "/home/akp66103/.../q8tea7_ATP",
    "/home/akp66103/.../q8wz42_ATP",
    "/home/akp66103/.../q92519_ATP",
    "/home/akp66103/.../q96c45_ATP",
    "/home/akp66103/.../q96qs6_ATP",
    "/home/akp66103/.../q9bxu1_ATP",
    "/home/akp66103/.../q9c0k7_ATP",
    "/home/akp66103/.../q9nsy0_ATP",
    "/home/akp66103/.../q9uhy1_ATP",
    "/home/akp66103/.../q9y243_ATP",
    "/home/akp66103/.../q9y616_ATP"
  ],
  "labels": [
    "o15197_ATP",
    "o43187_ATP",
    "o60674_ATP",
    "p00533_ATP",
    "p17612_ATP",
    "p21860_ATP",
    "p23458_ATP",
    "p24941_ATP",
    "p25092_ATP",
    "p28482_ATP",
    "p29597_ATP",
    "p51841_ATP",
    "p52333_ATP",
    "q05823_ATP",
    "q13308_ATP",
    "q13418_ATP",
    "q58a45_ATP",
    "q5jzy3_ATP",
    "q6vab6_ATP",
    "q7rtn6_ATP",
    "q7z7a4_ATP",
    "q8iv63_ATP",
    "q8ivt5_ATP",
    "q8nb16_ATP",
    "q8ncb2_ATP",
    "q8ne28_ATP",
    "q8tea7_ATP",
    "q8wz42_ATP",
    "q92519_ATP",
    "q96c45_ATP",
    "q96qs6_ATP",
    "q9bxu1_ATP",
    "q9c0k7_ATP",
    "q9nsy0_ATP",
    "q9uhy1_ATP",
    "q9y243_ATP",
    "q9y616_ATP"
  ],
  "overlay_plots": [
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/sequence_phylo_tree.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/classification_clusters_pca.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/classification_dendrogram_heatmap.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/classification_phylo_tree.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/ref_fel_pock_com_distance_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/ref_fel_pock_hbonds_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/ref_fel_pock_sasa_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/ref_fel_pock_ligand_residence_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/ref_fel_pock_ligand_axis_angle_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/ref_fel_pock_rmsf_by_cluster.png",
    "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/analysis/dccm_comparison.png"
  ],
  "working_dir": ".",
  "output_file": "combined_report.html",
  "title": "Combined MD Analysis of 37 Human Protein\u2013ATP Holo Structures",
  "enriched_prompt": "Rephrased Goal (3\u20116 sentences)\n\n1. **Preprocessing**: For each of the 37 PDBs, extract only the protein, ligand (ATP), and ions, excluding any water molecules.\n2. **Simulation Setup (simsetup)**: Build GROMACS inputs (topology, coordinates, .mdp, and .tpr) using AMBER99SB\u2011ILDN, TIP3P, 310\u202fK, 1\u202fbar, 0.15\u202fM NaCl, cubic box with 1.2\u202fnm buffer; solvate and add ions to neutralise the system.\n3. **HPC**: Submit two independent 200\u2011ns production MD replicates per system (74 trajectories total), monitor, and confirm all 200\u2011ns trajectories are fully generated (no truncation).\n4. **Analysis**: Map the ATP\u2011binding pocket from KAPCA (p17612) onto all proteins via a MAFFT/star MSA; plot the global and pocket\u2011mapped MSAs. Compute, for each system (averaged over the two replicates), the ten scalar descriptors: ATP COM distance statistics, ATP\u2011pocket axis angles, pocket \u03c7\u2081 circular mean & std, consensus\u2011mapped C\u03b1 RMSF mean & std, N\u2011lobe \u2194 C\u2011lobe DCCM mean, and shared\u2011reference dihedral PCA metric. Assemble a feature table, perform Ward hierarchical clustering, and generate a dendrogram and IQR\u2011scaled heatmap (optionally marking a k\u202f=\u202f4 cut).\n5. **Reporter**: Compile all results, plots, and a brief literature context into a single HTML report, ensuring the full 200\u2011ns data and all ten descriptors are included.",
  "user_goal": "I have 37 human protein\u2013ATP holo structures in given working directory (one PDB per system). There are 32 pseudokinases and 5 ground-truth active kinases. Please run a full end-to-end comparative MD study on all of them."
}
```

