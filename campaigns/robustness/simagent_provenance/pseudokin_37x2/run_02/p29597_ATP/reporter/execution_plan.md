# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requires a single‐simulation HTML report that automatically embeds images and statistics from the existing analysis_summary.jsonl file. The only mandatory data source is the JSONL; no new simulations or preprocessing are needed. A concise two‑step workflow suffices: read the summary, then generate the report. Optional literature context can be added later but is not required for the current deliverable.

## Overview

1. Parse the analysis_summary.jsonl file to obtain all scalar descriptors, image paths, and metadata. 2. Feed the parsed data to generate_html_report to produce a self‑contained, styled report named report.html.

## Report Focus

- Overall trends in ATP COM distance and orientation across the 37 holo structures
- Consensus‑mapped Cα RMSF distributions indicating flexible regions
- DCCM correlations between N‑lobe and C‑lobe dynamics
- Entropy of shared‑reference dihedral‑PCA as a measure of conformational heterogeneity

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to retrieve all per‑system metrics, image file paths, and statistical summaries.

**Reason:** Acquire the raw analysis data that the report will display.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds images, displays key statistics cards, and provides a clean, gradient‑styled layout.

**Reason:** Produce the final deliverable in the required reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

