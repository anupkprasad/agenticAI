# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The workflow requires a single‑simulation HTML report that pulls all analysis metadata and visualizations from the analysis summary, enriches it with relevant literature, and embeds everything in a clean, modern layout.  We will therefore (1) load the summary, (2) generate a targeted PubMed query, (3) fetch a handful of recent references, and (4) feed both the parsed data and the literature list into the HTML generator.  This keeps the process deterministic, avoids placeholder tools, and meets the directory and naming conventions specified.

## Overview

1️⃣ Parse `analysis/analysis_summary.jsonl`. 2️⃣ Create a PubMed query that references the protein (pseudokinase) and the analysis methods performed. 3️⃣ Retrieve up to 5 recent papers. 4️⃣ Generate `report.html` in the reporter directory, embedding all images, statistics, and literature references.

## Report Focus

- Dynamic behavior of the ATP binding pocket
- Inter‑lobe communication patterns revealed by DCCM
- Consensus pocket conformational variability across the 20 systems

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains the per‑system descriptors, statistics, and image paths.

**Reason:** We need all analysis data and image paths for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create prioritized PubMed search queries based on the protein type, analysis methods, and user hypothesis.

**Reason:** To produce a focused PubMed query that will return relevant literature.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP axis angles",
    "pocket \u03c71 statistics",
    "C\u03b1 RMSF",
    "DCCM lobe\u2011lobe",
    "dihedral\u2011PCA"
  ],
  "user_goal": "Analysis & Reporting Tasks for the 20 protein\u2013ATP holo complexes \u2013 extract dynamics descriptors and cluster the systems.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent articles that match the highest‑priority query.

**Reason:** We need actual literature references to embed in the report.

**Parameters:**
```json
{
  "query": "<TOP_PRIORITY_QUERY_FROM_PREVIOUS_STEP>",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML file that embeds all analysis figures, displays key statistics, and cites the literature.

**Reason:** Produce the final deliverable that meets the specified format.

**Parameters:**
```json
{
  "analysis_data": "<PARSED_DATA_FROM_FIRST_STEP>",
  "literature_refs": "<ARTICLES_FROM_SEARCH_PUBMED>",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

