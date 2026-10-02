# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

Fallback plan: Basic report generation without LLM planning

## Overview

Read analysis, optionally search literature, generate HTML report

## Report Focus

- Analysis results
- Key statistics

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse analysis_summary.jsonl file

**Reason:** Load analysis results

**Parameters:**
```json
{
  "summary_file": "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_5x2/run_02/p17612_ATP/analysis/analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries

**Reason:** Prepare for literature search

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF"
  ],
  "user_goal": "**Re\u2011phrased Goal (analysis \u2192 reporter only):**  \nFor each of the five protein\u2013ATP holo systems (p17612, o60674, p24941, q8ivt5, q13418) that already have two 200\u202fns MD trajectories, perform the specified analyses\u2014ligand pocket distance, consensus_dccm, consensus_rmsf, consensus_torsions, DCCM, dihedral_pca, nearby, protein RMSF\u2014using the ATP-binding pocket defined from the KAPCA reference (residues within 15\u202f\u00c5 of ATP) mapped onto each protein via MAFFT/star MSA.  \nCompute the ten required scalar descriptors (ATP COM distance stats, ATP\u2013pocket orientation stats, pocket \u03c7\u2081 circular mean/std, mean/std C\u03b1 RMSF of consensus-mapped residues, N\u2011/C\u2011lobe DCCM mean, shared-reference dihedral PCA dynamics scalar) by averaging over the two replicates and output each descriptor file with a standard basename into `/home/akp66103/.../analysis/`.  \nAggregate the ten descriptors for all five systems into a single feature table, perform Ward hierarchical clustering, and generate a dendrogram plus a robust z\u2011score/IQR\u2011scaled heatmap, saving these plots to the same analysis directory.  \nCompile a concise HTML report containing the clustering results, heatmap, and a brief literature context, and write it to `/home/akp66103/.../reporter/`.  \nAll analyses must treat the systems as holo complexes (include ATP, exclude crystallographic Mg/ions), use the default AMBER99SB-ILDN/TIP3P/310\u202fK/1\u202fbar/0.15\u202fM NaCl conditions, and assume the trajectories already exist\u2014no preprocessing, simulation, or HPC submission is performed."
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create HTML report from analysis data

**Reason:** Generate final report

**Parameters:**
```json
{
  "analysis_data": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

