# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that incorporates all scalar descriptors, time‑series plots, and a concise literature context. The analysis_summary.jsonl already contains the computed values, statistics, and image file paths, so the first step is to parse that file. To provide literature relevance, we will perform a targeted PubMed search using a query that reflects the system (pseudokinase ATP binding) and the analysis methods (molecular dynamics, ATP binding, pocket dynamics). Finally, we generate the HTML report, feeding it the parsed analysis data and the retrieved literature references. No other tools are needed for this workflow.

## Overview

1. Parse analysis results. 2. Fetch up to five recent PubMed papers relevant to pseudokinase ATP‑binding dynamics. 3. Create a comprehensive HTML report with embedded plots and key statistics.

## Report Focus

- ATP COM distance and orientation
- Pocket χ₁ orientation
- Consensus‑mapped Cα RMSF
- Lobe‑to‑lobe DCCM
- Shared‑reference dihedral PCA

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the analysis_summary.jsonl file to obtain all descriptor values, statistics, and image paths.

**Reason:** We need the analysis data to feed into the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Contextual Literature

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent PubMed entries that discuss pseudokinase ATP‑binding dynamics or related MD analyses.

**Reason:** Provides literature references to enrich the report.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding dynamics molecular dynamics",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, single‑simulation HTML report with embedded visualizations, key statistics, and literature citations.

**Reason:** The final deliverable.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

