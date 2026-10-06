# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has provided an analysis_summary.jsonl file containing all the computed metrics and the file paths to the plots. Our goal is to create a single, self‑contained HTML report that embeds those plots, presents key statistics, and situates the results within the current literature on ATP binding and allosteric regulation of ERBB3, VRK3, MLKL, and TITIN.  We will first parse the JSONL file to extract the data, then feed that structured data to the generate_html_report tool.  Literature queries are generated for context but not executed here; the user can run them separately if desired.

## Overview

A concise, professional HTML report that: 1) visualizes the apo‑vs‑holo comparison across all four proteins, 2) highlights the most informative statistics (mean, std, min, max for RMSD, RMSF, Rg, ATP‑COM distance, DCCM differences, DSSP changes), 3) embeds the overlay plots directly into the page as base64 images, and 4) includes a section of recent literature that contextualizes the observed dynamics.

## Report Focus

- Apo‑vs‑holo dynamics: RMSD, RMSF (150–200), radius of gyration, ATP‑COM distance
- Correlation of dynamic metrics with known ATP‑binding and activation‑loop conformations in ERBB3, VRK3, MLKL, and TITIN

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the provided analysis_summary.jsonl file to extract metrics, statistics, and image file paths.

**Reason:** We need the analysis data before we can generate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained report using the parsed analysis data.

**Reason:** This produces the final deliverable that the user can view and share.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

