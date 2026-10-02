# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis summary already contains all computed metrics, statistics, and paths to the relevant plot images. By parsing this JSONL file we obtain a structured dictionary that `generate_html_report` can consume directly. The report will embed the images as base64, display key statistics cards, and format the content with a clean, modern layout. No additional preprocessing or new calculations are required, and literature context can be added optionally, but the core deliverable is a self‑contained HTML file for each simulation.

## Overview

1. Read the `analysis_summary.jsonl` file. 2. Feed the parsed data to the HTML report generator, producing a `report.html` file in the dedicated `/reporter/` directory. 3. (Optional) Provide a list of PubMed queries for literature support if desired.

## Report Focus

- Key statistical descriptors per simulation (means, SDs, entropy, DCCM)
- Visual comparison of ligand‑pocket dynamics and protein flexibility
- Clustering insights and pseudokinase vs. active kinase context

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to extract all metrics, statistics, and image paths.

**Reason:** We need the full data dictionary for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds images, shows key statistics, and uses a modern layout.

**Reason:** This is the final deliverable required by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

