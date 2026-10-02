# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report must be built from the analysis results already present in the per‑simulation `analysis_summary.jsonl`. The only required steps are: 1) load that JSONL file to obtain all metrics, statistics and image paths; 2) feed the parsed data into `generate_html_report` which automatically embeds the figures and formats the output as a professional HTML document. 3) (Optional) a literature search can be performed to enrich the discussion, but it is not required for the basic report.

## Overview

This plan reads the per‑simulation analysis summary, optionally retrieves a few relevant literature references, and generates a self‑contained `report.html` containing embedded plots, key statistics cards, and a concise discussion.

## Report Focus

- Summary of the ten scalar dynamics descriptors
- Key statistical highlights (means, stds, min/max)
- Visual comparison of descriptor time‑series
- Discussion of clustering and functional implications

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to obtain metrics, statistics, and image paths.

**Reason:** Load the data that will drive the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report using the parsed data.  The report will automatically embed all referenced images and display key statistics cards.

**Reason:** Produce the final deliverable for the single simulation.

**Parameters:**
```json
{
  "analysis_data": "<to_be_filled_by_previous_step>",
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

