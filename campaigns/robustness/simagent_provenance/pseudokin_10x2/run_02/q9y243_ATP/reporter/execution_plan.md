# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis summary file contains all the quantitative results, statistics, and file paths to the generated plots. The report must embed these visualizations, present key statistics in an accessible format, and optionally provide literature context. Since the workflow is single‑simulation, only the `generate_html_report` tool is required after parsing the summary with `read_analysis_summary`.

## Overview

1. Load the `analysis_summary.jsonl` file to extract numerical metrics and plot paths. 2. Optionally generate PubMed queries to enrich the report with recent literature. 3. Use `generate_html_report` to produce a self‑contained `report.html` that embeds the images, displays the key statistics in cards, and provides a concise narrative of the findings.

## Report Focus

- ATP‑COM distance dynamics
- Pocket‑axis angle & χ1 conformation
- Consensus RMSF and DCCM
- Dihedral PCA entropy

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to retrieve analysis results, statistics, and image paths.

**Reason:** Need the analysis data for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report using the parsed data.

**Reason:** Generate the final deliverable.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

