# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user’s workflow requires a single‑simulation report that aggregates the analysis data stored in `analysis_summary.jsonl`. We need to read this file, parse all statistical summaries and image paths, and embed the resulting visualisations into a clean HTML report. Optional literature enrichment can be added, but the core deliverable is the HTML file. The plan below uses only the mandatory tools (`read_analysis_summary` and `generate_html_report`) and follows the path conventions specified in the prompt.

## Overview

1. Load the analysis summary (JSONL). 2. Pass the parsed data to the HTML report generator, which automatically embeds plots, displays key statistics, and formats the output as a professional scientific report.

## Report Focus

- Backbone RMSD and overall protein stability
- Residue‑level flexibility (RMSF) of the activation loop (residues 150–200)
- ATP–pocket dynamics (COM distance) in holo systems
- Correlation of backbone motions (DCCM) and its changes upon ligand binding
- Secondary‑structure evolution (DSSP) over the trajectory

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to obtain all analysis results, statistics, and image file paths.

**Reason:** The report must be built from the actual analysis results recorded during the MD trajectory evaluation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all plots, displays key statistics cards, and arranges the content into modern, organized sections.

**Reason:** This tool automatically embeds images as base64 and formats the report according to the specified styling guidelines.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

