# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that embeds all trajectory analyses, key statistics, and literature context. The analysis data are already in `analysis/analysis_summary.jsonl`. We first parse that file, then optionally augment the report with recent MD‑simulation literature on pseudokinase ATP binding. Finally, we generate the report with the provided tool.

## Overview

1. Read the pre‑generated analysis summary. 2. Search PubMed for recent literature on pseudokinase ATP molecular dynamics. 3. Generate a comprehensive HTML report that embeds all images and highlights the key statistics.

## Report Focus

- Dynamic descriptors of ATP binding
- Pocket χ1 torsion statistics
- Cα RMSF and DCCM correlations
- Clustering of the 20 pseudokinase systems

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the JSONL file containing all descriptor values, statistics, and image file paths.

**Reason:** We need the analysis data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve a handful of recent papers that discuss pseudokinase ATP dynamics to provide literature context.

**Reason:** The report should include a concise literature background.

**Parameters:**
```json
{
  "query": "pseudokinase ATP molecular dynamics",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a modern, self‑contained HTML report with embedded images, key statistics, and literature citations.

**Reason:** This produces the final deliverable the user requested.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

