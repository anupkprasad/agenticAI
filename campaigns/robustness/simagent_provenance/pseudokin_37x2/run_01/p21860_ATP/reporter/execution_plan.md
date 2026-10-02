# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report requires only per‑simulation data, which is already summarized in analysis_summary.jsonl. The plan therefore reads this file, optionally gathers literature for context, and generates a comprehensive HTML report embedding the provided plots and statistics.

## Overview

1. Load the analysis summary JSONL file. 2. (Optional) Perform targeted PubMed searches to enrich the narrative. 3. Generate a single‑simulation HTML report, saving it as report.html in the reporter directory.

## Report Focus

- ATP‑binding pocket dynamics
- Consensus DCCM and RMSF patterns

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all computed metrics, statistics, and image paths for this simulation.

**Reason:** Need the full analysis payload for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search Literature (Optional)

**Tool:** `search_pubmed`

**Description:** Retrieve recent PubMed articles that discuss ATP‑binding kinase simulations and the specific analytical methods used (RMSF, DCCM, etc.).

**Reason:** Provide context and citations in the report.

**Parameters:**
```json
{
  "query": "protein kinase ATP simulation RMSF DCCM",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, styled report that embeds all analysis visualisations, presents key statistics, and includes literature references.

**Reason:** Deliver the final, reader‑friendly output.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

