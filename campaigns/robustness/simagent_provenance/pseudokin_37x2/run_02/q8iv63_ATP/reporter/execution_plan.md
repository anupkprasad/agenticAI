# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a concise HTML report that embeds all visualizations and statistics from the pre‑computed trajectory analysis. The analysis data are already stored in the standard JSONL file `analysis/analysis_summary.jsonl`. The report can be generated directly from this data without additional literature searches, as the user’s primary goal is to visualize and summarize the results. Therefore, the workflow consists of two deterministic steps: parsing the summary file and generating the HTML report.

## Overview

1. Read and parse the analysis summary. 2. Create a comprehensive HTML report (`report.html`) in the `reporter/` directory that embeds all figures, displays key statistics, and presents the data in a modern, professional layout.

## Report Focus

- Visualization of dynamic descriptors across all 37 holo complexes
- Presentation of key statistical summaries (means, stds, ranges)
- Integration of robust‑scaled heatmaps and dendrograms

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the JSONL file that contains all per‑system descriptors, statistics, and image paths.

**Reason:** We need the parsed data to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Produce a self‑contained HTML file that embeds all analysis images, displays key statistics, and presents the information in a clear, modern layout.

**Reason:** This is the final deliverable requested by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

