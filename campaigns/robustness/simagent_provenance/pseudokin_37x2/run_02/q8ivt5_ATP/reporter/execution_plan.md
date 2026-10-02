# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl already contains all computed scalar descriptors, statistics, and image paths for each trajectory replica. To produce a concise, self‑contained HTML report we simply need to parse this file and feed the resulting data into the `generate_html_report` tool. The report will automatically embed images, display key statistics cards, and organize the content by analysis type. A literature context section is optional; if desired, we can generate targeted PubMed queries, but it is not mandatory for the per‑simulation report.

## Overview

1️⃣ Read the analysis_summary.jsonl file.
2️⃣ Pass the parsed data to `generate_html_report` to create `report.html` inside the reporter directory. The report will feature embedded plots, statistics, and a modern layout. Optionally, generate PubMed queries to enrich the report with recent literature.

## Report Focus

- ATP binding‑site dynamics (COM distance & axis angle)
- Pocket χ₁ torsion variability
- Consensus‑mapped Cα RMSF
- Lobe DCCM correlations
- Dihedral‑PCA entropy

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing per‑replica results and image paths.

**Reason:** Need to load the analysis results and image references.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report using the parsed analysis data.

**Reason:** Produce the final, self‑contained report with embedded visualizations.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

