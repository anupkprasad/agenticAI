# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The task requires creating a single‑simulation HTML report that embeds all visualisations and key statistics extracted from the `analysis_summary.jsonl` file. The workflow is straightforward: first read and parse the summary file, then generate the report using the provided tool. Optionally, literature queries can be added to enrich the context, but the core deliverable is the report.

## Overview

1) Read analysis summary → 2) Generate comprehensive HTML report. (Optional: add literature search and embed references.)

## Report Focus

- Overview of dynamic descriptors (distance, orientation, RMSF, DCCM, PCA)
- Key clustering insights (dendrogram, heatmap, k=4 clusters)
- Literature context for each pseudokinase

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to obtain all analysis results, statistics, and image file paths.

**Reason:** Need to load the analysis data that will feed the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, self‑contained HTML report that embeds all plots, displays key statistics cards, and includes a concise literature context for the kinase.

**Reason:** Produce the final deliverable required by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

