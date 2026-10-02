# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis summary already contains all computed scalar descriptors, cluster information, and image paths. The `read_analysis_summary` tool will parse this file into a structured dictionary that can be passed directly to `generate_html_report`.  Since the user did not request a combined report across multiple simulations, we use `generate_html_report` for the per‑system HTML output.  Optional literature context can be added by generating PubMed queries and attaching the resulting references, but the core deliverable is the HTML report with embedded visualizations and statistics.

## Overview

1️⃣ Load analysis results from `analysis/analysis_summary.jsonl`.  
2️⃣ Feed the parsed data to the HTML report generator, specifying a comprehensive report format and the output filename `report.html`.  
The resulting report will include embedded plots, key statistic cards, and a modern layout, all stored in the `/reporter/` directory.  Optional literature queries are prepared for later lookup.

## Report Focus

- Key descriptor statistics (mean & SD of ATP distance/orientation, χ1, RMSF, DCCM, PCA distance)
- Hierarchical clustering results (dendrogram, heatmap)
- Embedded visualizations (box‑plots, correlation matrices, cluster heatmap)

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing all descriptor statistics, cluster data, and image file paths.

**Reason:** Need to load analysis results into a structured dict.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a concise, visually rich HTML report embedding all plots and statistics.

**Reason:** Produce the final user‑facing report in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

