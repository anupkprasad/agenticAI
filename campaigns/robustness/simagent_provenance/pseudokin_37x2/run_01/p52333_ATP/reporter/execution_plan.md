# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report generation workflow requires only the already‑generated analysis data stored in `analysis/analysis_summary.jsonl`.  We first read and parse that JSONL file to extract all metrics, statistics, and image file paths.  These are then passed directly to the `generate_html_report` tool, which automatically embeds the images (converted to base64), inserts the key statistics as cards, and formats the report in a clean, professional layout.  No new simulations or preprocessing steps are needed, and literature searching is optional – it can be omitted to keep the pipeline simple and deterministic.

## Overview

1. Read `analysis_summary.jsonl`. 2. Pass parsed data to the report generator. 3. Output `report.html` in the reporter directory.

## Report Focus

- Ligand‑pocket dynamics (distance, angle, χ₁)
- Protein backbone flexibility (Cα RMSF)
- Correlated motions (DCCM, dihedral PCA)
- Family‑modular descriptor comparison

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the JSONL file containing all analysis results and image paths.

**Reason:** Obtain the analysis data required for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all analysis visualisations and key statistics.

**Reason:** Produce the final, self‑contained scientific report.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

