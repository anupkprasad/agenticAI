# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The goal is to produce a single‑simulation HTML report that presents the averaged scalar dynamics descriptors and their full‑200‑ns plots.  All data and image paths are stored in the local `analysis/analysis_summary.jsonl`.  The only required steps are: 1) read and parse that summary file, and 2) feed the parsed data to `generate_html_report`, which will embed the plots, create statistics cards, and add a concise literature context if references are supplied.  Because the user did not explicitly request a literature search, we pass an empty reference list, keeping the workflow simple and deterministic.

## Overview

Read analysis summary → Generate comprehensive HTML report (report.html) in the reporter directory.

## Report Focus

- Averaged scalar dynamics descriptors
- Full‑200‑ns trajectory plots
- Key statistical insights

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to extract analysis results, statistics, and image file paths.

**Reason:** Need the analysis data and plot paths to build the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds all plots, displays key statistics, and adds a brief literature context.

**Reason:** Produce the final deliverable in the required format.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

