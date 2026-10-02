# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user’s goal is to produce a single HTML report summarising the 20 × 2 ATP‑holo trajectory analyses. The required data already exist in `analysis/analysis_summary.jsonl`. The report will embed the visualisations, display the key statistics, and provide a concise literature context. To enrich the report, we will perform a brief PubMed search for recent literature on kinase pseudokinases and MD‑based functional analyses.

## Overview

1. Parse the analysis summary JSONL. 2. Generate a comprehensive HTML report embedding plots, statistics and literature references. 3. Include a literature search step to pull recent peer‑reviewed papers on pseudokinase dynamics and MD‑based functional annotation.

## Report Focus

- ATP‑pocket dynamic descriptors and their variance across systems
- Hierarchical clustering results and identification of four major dynamic clusters
- Functional implications for pseudokinase versus active kinase behaviour

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse `analysis/analysis_summary.jsonl` to extract per‑system descriptors, clustering results, and image file paths.

**Reason:** We need the analysis data and image references for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries tailored to the protein family and the analytical methods used.

**Reason:** To obtain recent literature that contextualises the findings.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCAs",
    "ATP\u2011pocket dynamics"
  ],
  "user_goal": "Summarise ATP\u2011pocket dynamics and clustering of kinase/pseudokinase holo\u2011trajectories",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve abstracts and metadata for the top PubMed hits generated in the previous step.

**Reason:** Collect contemporary references to include in the report.

**Parameters:**
```json
{
  "query": "pseudokinase ATP dynamics molecular dynamics",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional HTML report titled `report.html` that includes the dendrogram, heatmap, per‑system descriptor tables, key statistics cards, and the literature context.

**Reason:** The final deliverable must be a single HTML file containing all requested visualisations and insights.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "enriched_prompt": "Generate a scientific report summarising ATP\u2011pocket dynamics and clustering for 20 kinase/pseudokinase holo\u2011trajectories, with literature context on pseudokinase function and MD analyses."
}
```

