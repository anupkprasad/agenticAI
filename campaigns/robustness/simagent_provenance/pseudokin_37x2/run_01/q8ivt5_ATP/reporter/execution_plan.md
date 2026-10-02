# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that aggregates all analysis results from the existing `analysis_summary.jsonl`. The workflow requires first reading that file, then feeding the parsed data to the report generator. Literature search is optional and not mandatory for the report; therefore the simplest deterministic plan is to skip it. This keeps the process lightweight while meeting the specified deliverables.

## Overview

Generate a comprehensive, self‑contained HTML report for one MD simulation by reading the existing analysis summary and invoking the dedicated report generation tool.

## Report Focus

- Summary of key metrics (means, SDs, extrema)
- Embedded plots for each analysis type
- Interpretation of ligand–pocket dynamics
- Comparison with literature (if available)

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to extract all analysis metrics, statistics, and image file paths.

**Reason:** Need to load all analysis results to pass to the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report embedding the parsed analysis data and all visualizations.

**Reason:** Produce the final deliverable as specified.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

