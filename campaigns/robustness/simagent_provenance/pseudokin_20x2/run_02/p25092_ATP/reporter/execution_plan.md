# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report workflow requires only the parsed analysis results to generate a comprehensive HTML summary. Reading the JSONL file provides all metrics, image paths, and derived statistics. The `generate_html_report` tool automatically embeds images and produces the required layout. Optionally, literature search queries can be prepared for later use, but are not mandatory for the report generation.

## Overview

1. Load the analysis summary. 2. (Optional) Create PubMed/BioRxiv query strings for contextual literature. 3. Generate a single‑simulation HTML report in the reporter subdirectory.

## Report Focus

- ATP‑binding pocket dynamics
- Hierarchical clustering of descriptor space

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains the descriptor values, dendrogram, heat‑map, and image paths.

**Reason:** Need the full set of computed metrics and image references for report construction.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed and BioRxiv search queries to retrieve context about protein kinase dynamics and the applied analysis methods.

**Reason:** Optional literature context can be incorporated later or referenced in the report.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "clustering"
  ],
  "user_goal": "Summarize the clustering of ATP\u2011binding pocket dynamics across 20 protein\u2013ATP holo systems.",
  "protein_name": "protein kinase",
  "analysis_stats": {}
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds the dendrogram, heat‑map, and key statistics cards, using the parsed analysis data.

**Reason:** Produce the final deliverable in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

