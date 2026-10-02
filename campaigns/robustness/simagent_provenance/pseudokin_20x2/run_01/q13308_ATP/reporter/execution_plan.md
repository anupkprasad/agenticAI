# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report requires only the analysis results that have already been computed and stored in `analysis_summary.jsonl`. We first read and parse this file to obtain all statistical values and image paths. Then we feed the parsed data directly to `generate_html_report`, which will embed the images, display key statistics, and format the content in a professional, comprehensive layout. No additional preprocessing or external data is needed for a single‑simulation report, so we keep the workflow minimal and deterministic.

## Overview

Generate a single‑simulation HTML report for the q13308_ATP system by (1) parsing the existing analysis summary and (2) rendering the report with embedded visualisations and statistics.

## Report Focus

- ATP‑pocket interaction metrics
- Pocket residue dynamics
- Inter‑lobe correlation
- Consensus‑mapped flexibility

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the `analysis_summary.jsonl` file that contains all computed descriptors, statistics, and image file paths for the two 200 ns replicates.

**Reason:** Retrieve all analysis data needed for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report (`report.html`) that embeds the trajectory plots, displays key statistics cards, and uses a modern layout with visual hierarchy.

**Reason:** Produce the final deliverable as specified.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": null,
  "final_impression": null,
  "pdb_data": null,
  "enriched_prompt": null
}
```

