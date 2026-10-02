# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a concise HTML report that summarizes the per‑simulation descriptors stored in `analysis_summary.jsonl`. The required workflow is to parse that file, optionally add literature context, and then generate the report with embedded visualisations. No new MD calculations or combined‑simulation steps are needed, so only two tool invocations are necessary: `read_analysis_summary` and `generate_html_report`.

## Overview

1. Load the analysis summary file. 2. Pass the parsed data to the report generator to create a self‑contained HTML file named `report.html` in the reporter directory. 3. (Optional) Provide a list of literature references if desired.

## Report Focus

- Summary of the 10 scalar descriptors per system
- Visual representations of descriptors and clustering results
- Brief literature context linking MD observations to known kinase behaviour

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all computed descriptors, statistics and image file paths for this single simulation.

**Reason:** Load the complete set of results that will feed the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, self‑contained HTML report that embeds all plots, displays key statistics, and optionally includes literature references.

**Reason:** Produce the final deliverable required by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

