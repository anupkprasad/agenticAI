# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The per‑simulation report requires only the analysis summary for the specific trajectory and the ability to embed the resulting plots and statistics into a polished HTML page. The analysis summary contains all computed descriptors, image paths, and metadata. By feeding this data directly to the `generate_html_report` tool, we avoid any unnecessary steps. Literature search is optional and not requested for this single‑simulation report, so it is omitted to keep the workflow straightforward.

## Overview

The plan reads the analysis summary from `analysis/analysis_summary.jsonl`, parses it into a structured dictionary, and passes that dictionary to the HTML report generator to produce `report.html` in the reporter directory. The report will automatically embed images, display key statistics, and structure the content by analysis type.

## Report Focus

- ATP binding pocket dynamics
- Consensus RMSF and DCCM relationships
- Clustering outcome and heat‑map interpretation

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing all analysis results and image file paths.

**Reason:** Load all analysis outputs and metadata needed for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report from the parsed analysis data.

**Reason:** Produce the final deliverable with embedded visualizations and statistics.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

