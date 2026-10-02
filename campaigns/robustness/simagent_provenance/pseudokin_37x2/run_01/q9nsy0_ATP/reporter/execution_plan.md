# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that includes all analysis results, embedded visualisations, and optional literature context. The analysis data are already stored in `analysis/analysis_summary.jsonl`. We can parse this file, extract the statistics and image paths, and feed the parsed data directly into the `generate_html_report` tool. Literature searching is optional; for brevity we omit it but note that the report generation tool can accept a list of references if desired.

## Overview

1. Load the JSONL analysis summary. 2. Feed the parsed data into the HTML generator, producing a polished report with embedded plots and statistics. 3. The report will be saved as `report.html` in the reporter directory.

## Report Focus

- Ligand‑Pocket Interactions
- Consensus Dynamics & RMSF
- Dihedral PCA Landscape

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing analysis results, statistics, and image paths.

**Reason:** We need the raw analysis data to build the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report with embedded visualisations and key statistics.

**Reason:** This produces the final deliverable in the required format.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

