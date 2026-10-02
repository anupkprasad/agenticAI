# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already performed all trajectory analyses and stored the results in `analysis/analysis_summary.jsonl`. The only remaining tasks are to parse that file, optionally gather relevant literature, and produce a self‑contained HTML report. The workflow therefore consists of two deterministic steps: reading the summary and generating the report. Literature queries can be added as an optional step if further context is desired.

## Overview

1. Load the analysis results from `analysis/analysis_summary.jsonl`. 2. (Optional) Generate PubMed/BioRxiv queries based on the analysis types and protein names to fetch contextual literature. 3. Pass the parsed data (and any literature references) to `generate_html_report`, which will embed all plots, statistics, and literature snippets into `report.html` within the dedicated reporter directory.

## Report Focus

- Summary of the six consensus descriptors across the 20 proteins
- Visualization of the dendrogram and heat‑map
- Contextual literature highlights for each protein system

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all per‑replicate statistics, aggregated descriptors, and image paths.

**Reason:** We need the full set of computed descriptors and the paths to the generated plots to construct the report.

**Parameters:**
```json
{
  "summary_file": "analysis/analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all visualizations, displays key statistics, and includes brief literature context.

**Reason:** This is the final deliverable that the user requested.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

