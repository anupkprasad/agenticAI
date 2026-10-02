# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl file contains all the pre‑computed scalar descriptors, visualisations, and metadata for the 20 holo‑kinase systems. To produce a polished, self‑contained HTML report we only need to parse this summary, optionally augment it with recent literature on kinase ATP‑binding dynamics, and feed both into the generate_html_report tool. No re‑analysis or re‑simulation is required, so the workflow remains straightforward yet comprehensive.

## Overview

1️⃣ Read the pre‑computed analysis summary. 2️⃣ Query PubMed for recent MD simulation studies of kinase ATP binding. 3️⃣ Generate a single‑simulation HTML report that embeds all plots, displays key statistics, and cites relevant literature.

## Report Focus

- Summary of ATP‑binding dynamics descriptors
- Pocket mapping and consensus torsion analysis
- Hierarchical clustering and dendrogram interpretation

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis/analysis_summary.jsonl` file to obtain all descriptor values, statistical summaries, and image paths.

**Reason:** Load the analysis results that will populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Relevant Literature

**Tool:** `search_pubmed`

**Description:** Retrieve recent articles that discuss MD simulations of kinase ATP‑binding dynamics to provide context and validation.

**Reason:** Augment the report with up‑to‑date literature citations.

**Parameters:**
```json
{
  "query": "kinase ATP binding MD simulation",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report embedding all analysis plots, key statistic cards, and literature references.

**Reason:** Produce the final deliverable with visualisations and narrative.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

