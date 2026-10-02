# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report must summarize the per‑simulation analysis stored in analysis_summary.jsonl and provide brief literature context for the pseudokinase and active kinase systems.  We therefore first parse the summary file, then retrieve a small set of relevant PubMed references, and finally generate a single, self‑contained HTML report using the provided `generate_html_report` tool.

## Overview

Generate a comprehensive HTML report for the 37 ATP‑bound protein trajectories.  The report will embed all analysis plots, display key statistics, and include a short literature background.

## Report Focus

- Ligand‑pocket distance distributions
- Consensus RMSF and torsion profiles
- DCCM clustering and feature heat‑map

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all metric results and image file paths for the 37 trajectories.

**Reason:** Load the full set of analysis results into memory.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Contextual Literature

**Tool:** `search_pubmed`

**Description:** Retrieve a handful of recent papers on pseudokinase and active kinase dynamics involving ATP binding, to provide brief background in the report.

**Reason:** Gather relevant literature to cite in the report.

**Parameters:**
```json
{
  "query": "pseudokinase ATP molecular dynamics",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a single HTML file that embeds all analysis visualisations, presents key statistics in card format, and includes the literature references.

**Reason:** Produce the final deliverable.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

