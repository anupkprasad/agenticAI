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
  "summary_file": "/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_10x2/run_01/o60674_ATP/analysis/analysis_summary.jsonl"
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
  "user_goal": "**Analysis & Reporting Goal (JAK2 + 9 additional holo kinases)**  \n1. Load the two 200\u2011ns production trajectories (rep01, rep02) for each of the ten protein\u2013ATP holo structures (including ligand, excluding crystallographic ions).  \n2. Using the KAPCA (p17612) pocket definition (residues \u226415\u202f\u00c5 from ATP), map the consensus pocket onto every system via a global MSA (MAFFT/star); identify the corresponding pocket residues and compute:  \n   * ATP COM distance mean & std. dev.  \n   * ATP orientation mean & std. dev. relative to the pocket axis  \n   * Pocket side\u2011chain \u03c7\u2081 circular mean & std. dev.  \n   * Flexibility (mean & std. dev. of RMSF) of consensus\u2011mapped C\u03b1 atoms  \n   * N\u2011lobe \u2194 C\u2011lobe DCCM mean correlation  \n   * Shared\u2011reference \u03c6/\u03c8/\u03c7\u2081 dihedral PCA scalar versus KAPCA (pca_pka_ref_shared_dyn).  \n   Average these ten descriptors over the two replicates for each protein.  \n3. Assemble the 10\u2011descriptor feature table, perform Ward hierarchical clustering, and generate a dendrogram (full tree) plus a robust z\u2011score/IQR\u2011scaled feature heatmap, marking a k\u202f=\u202f4 cut for interpretation.  \n4. Produce a single HTML report containing: the dendrogram + heatmap panel, brief literature context for each kinase, and a concise summary of the clustering results.  \n\nAll analyses respect the protein_with_ligand case: ligand included, crystallographic ions omitted, and trajectories are used as supplied. No preprocessing, simulation setup, or new MD runs are performed."
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

