# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already supplied an analysis_summary.jsonl file containing all scalar descriptors, statistics, and image paths. The report should simply parse this summary and feed it into the generate_html_report tool to produce a comprehensive HTML document. No further data manipulation or literature search is required for this single‑simulation report, keeping the workflow straightforward and deterministic.

## Overview

1. Read the analysis_summary.jsonl file to obtain a structured dictionary of all results and image locations.
2. Pass the parsed data to generate_html_report, requesting a comprehensive report named report.html. The tool will automatically embed images and create the visual layout.
3. The resulting HTML file will be written to the reporter directory under the working directory specified by the caller.

## Report Focus

- Summary of key scalar descriptors (means & SDs)
- Visualization of pocket‑ATP interactions (distance/orientation)
- Side‑chain χ₁ distribution across mapped pocket residues
- Consensus Cα RMSF heatmap
- N‑lobe ↔ C‑lobe DCCM correlation plot
- Shared‑reference dihedral PCA scalar trend

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to load all metrics, statistics, and image paths into a dictionary.

**Reason:** Need to load the pre‑computed analysis results for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report from the parsed analysis data.

**Reason:** Generate the final deliverable with embedded visualizations and key statistics.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

