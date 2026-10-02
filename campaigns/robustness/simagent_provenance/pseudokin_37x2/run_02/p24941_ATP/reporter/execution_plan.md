# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To produce a per‑simulation HTML report we need only the analysis results stored in the `analysis_summary.jsonl` file. The report generator can embed all plots, compute key statistics and render a concise, professional page. Literature searching is optional; omitting it keeps the workflow lightweight while still producing a complete, self‑contained report.

## Overview

Read the pre‑generated analysis summary, feed the parsed data to the report generator, and output a `report.html` file in the simulation’s `/reporter` folder. The report will contain embedded images, key statistics cards, and a modern layout.

## Report Focus

- ATP‑COM distance
- ATP‑axis angle
- Pocket χ1
- Consensus‑mapped Cα RMSF
- N‑lobe ↔ C‑lobe DCCM
- Shared‑reference φ/ψ/χ1 PCA dynamics

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all analysis metrics, statistics, and image paths for the current simulation.

**Reason:** Load all analysis results that the report must display.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all images, shows key statistics, and provides a clean, professional layout.

**Reason:** Generate the final deliverable that can be viewed in a browser.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

