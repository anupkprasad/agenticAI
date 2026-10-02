# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report is generated from a pre‑computed `analysis_summary.jsonl` that contains all scalar descriptors, feature tables, and paths to the dendrogram and heatmap images.  The `generate_html_report` tool automatically extracts image paths and embeds them as base64, so the only required input is the parsed analysis data.  Literature context is optional; a brief PubMed search on ‘protein MD simulation kinase’ will provide a few recent references to insert into the report.  The workflow is therefore: parse the summary, optionally query PubMed, and call `generate_html_report` with the parsed data and reference list.

## Overview

1. Load `analysis_summary.jsonl`.
2. Optionally perform a PubMed search for recent kinase MD literature.
3. Call `generate_html_report` to produce `report.html` in the reporter directory, embedding all visualizations and key statistics.

## Report Focus

- Consensus pocket dynamics (COM distance & orientation)
- Side‑chain flexibility (χ1 angles & RMSF)
- Inter‑lobe communication (DCCM correlation)
- Entropy of shared dihedral motions

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to obtain the per‑system metrics, feature table, and paths to the dendrogram and heatmap images.

**Reason:** All subsequent steps require the full set of analysis results.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Context

**Tool:** `search_pubmed`

**Description:** Retrieve a handful of recent (last 5 yrs) publications on kinase MD simulations to enrich the literature paragraph in the report.

**Reason:** Provides up‑to‑date literature to contextualise the findings.

**Parameters:**
```json
{
  "query": "kinase MD simulation",
  "max_results": 3,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds the dendrogram and heatmap images, displays key statistics for each descriptor, and includes the literature paragraph.

**Reason:** Produces the final deliverable in the reporter directory.

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

