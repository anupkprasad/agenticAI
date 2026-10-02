# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis summary file contains all numeric descriptors, image paths, and per‑trajectory statistics that are required for the report.  After loading this data we enrich the narrative with recent, relevant literature using a PubMed search on pseudokinase ATP‑binding dynamics and associated MD analysis methods.  Finally we call `generate_html_report` to create a single, self‑contained HTML file that embeds the plots and presents key statistics in a clean, modern layout.

## Overview

1) Load the JSONL analysis summary; 2) Search PubMed for recent literature on pseudokinase ATP binding dynamics and MD descriptors; 3) Assemble the results into the `generate_html_report` call, producing `report.html` in the reporter directory.

## Report Focus

- Per‑system ATP COM distance (mean ± SD)
- ATP orientation (mean ± SD)
- Pocket χ1 (mean ± SD)
- Consensus Cα RMSF (mean ± SD)
- N‑lobe ↔ C‑lobe DCCM mean
- Shared‑reference dihedral PCA landscape entropy

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis summary JSONL to obtain metrics, image file paths, and statistical summaries.

**Reason:** Need the complete dataset for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Contextual Literature

**Tool:** `search_pubmed`

**Description:** Retrieve recent papers (last 10 years) that discuss pseudokinase ATP binding dynamics, MD‑derived descriptors such as RMSF, DCCM, dihedral PCA, and ATP COM distance analyses.

**Reason:** Provide up‑to‑date literature for the discussion section of the report.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding dynamics AND MD simulation AND (RMSF OR DCCM OR dihedral PCA)",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds all analysis images, presents key statistics, and cites the retrieved literature.

**Reason:** Produce the final deliverable as a self‑contained HTML file.

**Parameters:**
```json
{
  "analysis_data": "<OUTPUT_FROM_STEP_1>",
  "literature_refs": "<OUTPUT_FROM_STEP_2>",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

