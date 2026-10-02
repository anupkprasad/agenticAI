# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl file already contains all computed metrics and image paths. Generating the HTML report is a straightforward two‑step process: parse the summary, then feed the parsed data into generate_html_report. Optional literature searches are not mandatory for the core report, so they are omitted to keep the workflow simple and deterministic.

## Overview

1️⃣ Read the analysis summary from the provided JSONL file.
2️⃣ Use the parsed data to automatically create a comprehensive, well‑formatted HTML report (report.html) with embedded visualizations, key statistics, and modern layout.
3️⃣ (Optional) If additional literature context is desired, generate search queries, but this is not required for report generation.

## Report Focus

- ATP binding pocket metrics (COM distance & orientation)
- Pocket side‑chain χ₁ dynamics (circular mean & SD)
- Consensus‑mapped Cα RMSF & DCCM correlations
- Shared‑reference φ/ψ/χ₁ dihedral PCA dynamics scalar
- Ward hierarchical clustering & feature heatmap

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to extract all analysis results, statistics, and image file paths.

**Reason:** Need to load the analysis data that will populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report (`report.html`) from the parsed analysis data. The report will embed all relevant images, display key statistics cards, and format the content with a clean, professional layout.

**Reason:** Produce the final deliverable that meets the user’s reporting requirements.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

