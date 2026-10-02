# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report is generated from the already‑computed analysis data stored in analysis/analysis_summary.jsonl.  We first read and parse that file, then fetch relevant literature to provide context, and finally create a comprehensive HTML report that embeds all visualizations and key statistics.  This workflow requires only the three available tools and follows the path guidelines for per‑simulation reporting.

## Overview

Generate a self‑contained HTML report for the q92519 ATP‑bound simulation, highlighting ATP‑binding pocket dynamics, consensus‑mapped metrics, and structural fluctuations, supported by recent literature on pseudokinase ATP binding.

## Report Focus

- ATP binding pocket dynamics
- Consensus‑mapped pocket metrics
- Pseudokinase structural fluctuations

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the JSONL file containing all per‑replicate metrics, averages, and image paths.

**Reason:** Need the analysis data to feed the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Literature Search

**Tool:** `search_pubmed`

**Description:** Retrieve recent publications on pseudokinase ATP binding and MD‑based structural analysis to provide contextual background.

**Reason:** Provide up‑to‑date literature references for the report.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report with embedded plots, statistics cards, and literature context.

**Reason:** Produce the final deliverable.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html",
  "enriched_prompt": "Using the full 200\u202fns trajectory of q92519 ATP\u2011bound, analyze ATP binding pocket dynamics via consensus mapping to KAPCA, compute COM distance, orientation angle, side\u2011chain \u03c7\u2081 statistics, and shared\u2011reference PCA. Present scalar descriptors, RMSF, DCCM, and visualizations."
}
```

