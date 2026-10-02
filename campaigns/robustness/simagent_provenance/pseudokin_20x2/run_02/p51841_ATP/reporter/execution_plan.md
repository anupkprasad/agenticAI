# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl file contains all scalar descriptors, image paths, and summary statistics for the current simulation. The only required output for a single‑simulation report is an HTML file that embeds these visualisations and highlights key statistics. The workflow therefore consists of two deterministic steps: (1) parse the summary, (2) feed the parsed data into the HTML‑report generator. Literature queries are optional and are omitted to keep the process concise.

## Overview

Generate a comprehensive HTML report for the current protein‑ATP holo simulation by reading the analysis summary and passing the data to the report generator.

## Report Focus

- Scalar dynamics descriptors (RMSD, RMSF, DCCM, etc.)
- Pocket‑focused metrics and MSA visualisations
- Key statistical summaries and visual hierarchy

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to extract results, statistics, and image paths.

**Reason:** Load all analysis outputs needed for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create the final report with embedded images and key statistics.

**Reason:** Produce the deliverable report in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

