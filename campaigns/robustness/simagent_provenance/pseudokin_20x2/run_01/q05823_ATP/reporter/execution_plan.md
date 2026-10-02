# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The task requires a single‑simulation HTML report that incorporates the pre‑computed trajectory descriptors, embedded plots, key statistics, and literature context. The workflow will: 1) read the analysis summary; 2) generate PubMed query strings that match the protein context and the descriptors that were computed; 3) fetch relevant literature; and 4) assemble the report. All intermediate data are kept in memory and passed directly to the report generator, ensuring that no unnecessary files are written or read beyond the required inputs.

## Overview

1. Load analysis results from `/home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_20x2/run_01/q05823_ATP/analysis/analysis_summary.jsonl`. 2. Create PubMed queries based on the descriptors and the ATP‑binding protein context. 3. Retrieve a short set of recent, high‑impact references. 4. Feed the parsed analysis data and the literature references into `generate_html_report` to create `report.html` in the reporter directory.

## Report Focus

- Dynamic behavior of the ATP pocket across 200 ns production runs
- Comparison of descriptor averages between replicates and across the 20 holo systems
- Clustering of systems based on Ward’s method and robust‑scaled feature heatmap

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain all computed descriptors, statistics, and image paths.

**Reason:** We need the full analysis payload for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries

**Tool:** `generate_literature_queries`

**Description:** Create a list of targeted search queries that combine the protein context, MD simulation, and the descriptors used.

**Reason:** Structured queries increase the relevance of literature results.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DCCM",
    "Consensus Pocket Metrics",
    "Consensus Torsions"
  ],
  "user_goal": "Analyze ATP holo complexes and derive dynamic descriptors.",
  "protein_name": "ATP-binding protein",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve up to 5 recent references for each generated query to provide context for the analysis.

**Reason:** Recent literature informs the interpretation of the descriptors.

**Parameters:**
```json
{
  "query": "",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML file that embeds the analysis images, displays key statistics, and cites the literature.

**Reason:** The final deliverable is a self‑contained report.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

