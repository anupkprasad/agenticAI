# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report must summarize the quantitative descriptors from the 37‑system analysis, display the clustering dendrogram and heat‑map, and provide a concise literature context. The workflow therefore reads the already‑generated analysis_summary.jsonl, optionally queries PubMed for recent pseudokinase ATP‑binding studies, and then feeds the parsed data and literature citations into generate_html_report to produce a single, self‑contained HTML file.

## Overview

1️⃣ Load analysis results 2️⃣ Fetch a handful of relevant PubMed references 3️⃣ Generate the HTML report with embedded visualisations and key statistics.

## Report Focus

- ATP‑binding pocket stability across 37 pseudokinase systems
- Hierarchical clustering of functional descriptors
- Key structural descriptors (COM distance, orientation, χ₁, RMSF, DCCM, PCA entropy)
- Contextual literature on pseudokinase dynamics

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all scalar descriptors, statistics, and paths to the dendrogram/heat‑map images.

**Reason:** Need the analysis data for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Contextual Literature

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent articles on pseudokinase ATP‑binding dynamics and MD‑based functional clustering.

**Reason:** Provide up‑to‑date literature references that frame the analysis.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding molecular dynamics clustering",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds all images (dendrogram, heat‑map, any per‑system plots), displays key statistics cards, and includes the PubMed citations.

**Reason:** Produce the final deliverable for the reporter folder.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

