# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The per‑simulation workflow requires a single HTML report that embeds all figures and key statistics.  The analysis results are already collated in `analysis_summary.jsonl`.  The simplest and most deterministic approach is to read that file, feed the parsed data into the `generate_html_report` tool, and let the reporter handle figure embedding and layout.  Literature context is optional; if desired, queries can be generated and searched, but the primary deliverable is the HTML report.

## Overview

1. Parse the existing `analysis_summary.jsonl` to extract all numerical statistics, image paths, and metadata. 2. Call `generate_html_report` with the parsed data to produce a self‑contained `report.html` in the reporter sub‑directory.

## Report Focus

- Key scalar descriptors (COM distance, orientation, χ₁, RMSF, DCCM, PCA distance)
- Comparison of the two trajectory replicates
- Visualization of the pocket residues and their mapped positions

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the analysis results and statistics from `analysis_summary.jsonl`.

**Reason:** Need the parsed analysis data for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all plots, displays key statistics, and presents a clear, modern layout.

**Reason:** Produce the final deliverable in the expected format.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

