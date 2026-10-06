# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To create the final comparative report, we need to aggregate the pre‑computed analysis summaries and overlay plots from each of the eight MD runs. The `generate_combined_html_report` tool is designed for this purpose: it consumes the analysis JSONL files from each simulation directory, pulls in the specified overlay visualisations, and builds a self‑contained HTML document that includes the literature context automatically pulled from the analysis artefacts. No additional preprocessing or literature search is required at this stage, so we invoke the tool directly with the supplied directories, labels, and plot paths.

## Overview

A single-step, fully automated generation of a rich, self‑contained HTML report that collates all simulation analyses, visualisations, and literature references across the four human pseudokinases and their apo/holo states.

## Report Focus

- Dynamics of ATP binding on pseudokinases
- Activation‑loop conformations & allosteric regulation

## Execution Steps (1 steps)

### Step 1: Generate combined MD analysis report

**Tool:** `generate_combined_html_report`

**Description:** Create a comprehensive HTML report that aggregates analysis summaries, overlay plots, and literature references from all eight simulations.

**Reason:** This single tool call aggregates all the required data, visualisations, and literature context into the final HTML report.

**Parameters:**
```json
{
  "sim_dirs": [
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860/analysis",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/p21860_ATP_MG/analysis",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63/analysis",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8iv63_ATP_MG/analysis",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8nb16/analysis",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8nb16_ATP_MG/analysis",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8wz42/analysis",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8wz42_ATP_MG/analysis"
  ],
  "labels": [
    "ERBB3_Apo",
    "ERBB3_Holo",
    "VRK3_Apo",
    "VRK3_Holo",
    "MLKL_Apo",
    "MLKL_Holo",
    "TITIN_Apo",
    "TITIN_Holo"
  ],
  "overlay_plots": [
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/analysis/VRK3_dccm_diff_heatmap.png",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/analysis/MLKL_dccm_diff_heatmap.png",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/analysis/TITIN_dccm_diff_heatmap.png",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/analysis/com_distance_overlay.png",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/analysis/rg_overlay.png",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/analysis/rmsd_overlay.png",
    "/home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/analysis/rmsf_overlay.png"
  ],
  "working_dir": ".",
  "output_file": "combined_report.html",
  "title": "Comparative MD Analysis of Human Pseudokinases",
  "enriched_prompt": "You are the Reporter Agent in COMBINED multi-simulation mode. The study aims to compare the dynamics of apo versus holo states for four human pseudokinases (ERBB3, VRK3, MLKL, TITIN) using 1 ns MD simulations with AMBER99SB-ILDN, TIP3P water, 310\u202fK, 1\u202fbar, 0.15\u202fM NaCl. Analyses include backbone RMSD, per\u2011residue RMSF (active\u2011site 150\u2013200), radius of gyration, COM distance (holo), C\u03b1 DCCM, and DSSP. Generate overlay plots and statistical tables, retrieve relevant literature on activation\u2011loop conformations and allosteric regulation, and produce a final report correlating simulation findings with literature.",
  "user_goal": "Study the effect of ATP binding on protein dynamics for four pseudokinases by running 1\u2011ns MD simulations and analyzing key dynamical metrics, then compare the results and relate them to the literature on activation\u2011loop conformation and allosteric regulation.",
  "protein_name": "Human pseudokinases (ERBB3, VRK3, MLKL, TITIN)"
}
```

