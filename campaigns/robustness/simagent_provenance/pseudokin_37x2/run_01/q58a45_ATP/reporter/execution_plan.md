# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report generation workflow is straightforward: the per‑simulation analysis artifacts have already been produced and collected in `analysis/analysis_summary.jsonl`. The only tasks we need to perform are (i) load that JSONL file so that the `generate_html_report` tool can consume the analysis data and image paths, and (ii) invoke `generate_html_report` to produce a self‑contained `report.html` inside the dedicated `reporter/` subdirectory. Literature retrieval is optional and is omitted here to keep the pipeline focused on the required deliverable.

## Overview

Generate a single‑simulation comprehensive HTML report from the pre‑computed analysis summary.

## Report Focus

- Ligand pocket dynamics
- Consensus residue flexibility
- Dihedral PCA insights
- Clustering and heatmap visualisation

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis/analysis_summary.jsonl` file and retrieve the analysis results, statistics, and embedded image paths.

**Reason:** We need the structured analysis data for the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, self‑contained HTML report that includes embedded figures, key statistics cards, and a concise scientific narrative.

**Reason:** This is the final deliverable that will be placed in `reporter/`.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

