# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The task requires a single‑simulation HTML report. The analysis results and image paths are stored in `analysis/analysis_summary.jsonl`. We will parse this file, then feed the parsed data directly to `generate_html_report`. Literature search is optional; for completeness we can generate a few PubMed queries but they will not be mandatory for report generation. The final report will be written as `report.html` in the reporter directory.

## Overview

1. Read the analysis summary JSONL file. 2. Optionally create literature queries. 3. Generate a comprehensive HTML report containing embedded visualizations, key statistics, and a concise narrative.

## Report Focus

- ATP–pocket distance distribution
- ATP orientation relative to pocket axis
- Side‑chain χ₁ statistics
- Consensus‑mapped Cα RMSF
- N‑lobe ↔ C‑lobe DCCM mean
- Shared‑reference PCA dynamics

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to obtain all analysis descriptors and image paths.

**Reason:** Load all computed scalar dynamics descriptors and associated plots for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, comprehensive report embedding all plots, displaying key statistics, and summarizing the findings.

**Reason:** Produce the final deliverable that the user requests.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

