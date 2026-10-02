# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already completed all trajectory analyses and stored the results in a single `analysis_summary.jsonl` file. The only remaining task is to parse this file and generate a self‑contained HTML report that embeds all plots, presents the key scalar descriptors, and gives a concise literature context. No additional simulations or preprocessing are required. The plan therefore focuses on two straightforward tool calls: (1) read the summary file and (2) generate the HTML report. Optional literature queries are included for completeness, but they are not mandatory for the final deliverable.

## Overview

1. Parse the existing analysis summary. 2. Generate a comprehensive HTML report (`report.html`) that embeds all visualizations, displays key statistics, and (optionally) includes a brief literature review.

## Report Focus

- ATP‑pocket interaction descriptors (COM distance, orientation, side‑chain χ₁)
- Consensus RMSF and DCCM statistics
- Shared‑reference PCA dynamics versus KAPCA
- Integrated visualizations of the full 200‑ns trajectories

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to obtain the statistical results and image paths for the two 200‑ns trajectories.

**Reason:** Need to load the analysis data that will be fed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, comprehensive HTML report that includes embedded images, statistical cards, and a brief literature context.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

