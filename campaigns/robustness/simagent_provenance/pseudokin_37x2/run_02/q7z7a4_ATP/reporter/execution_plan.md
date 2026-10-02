# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The goal is to produce a concise yet comprehensive HTML report for the q7z7a4_ATP simulation.  We first load the analysis summary produced by the analysis agent, then generate literature queries that are relevant to the protein and the MD metrics calculated.  A PubMed search for the highest‑priority query will provide contextual references.  Finally, we feed the parsed analysis data and the literature citations into the `generate_html_report` tool to create the final `report.html` in the reporter directory.  The plan keeps steps linear, uses only the allowed tools, and adheres to the file‑path rules.

## Overview

1) Read the analysis_summary.jsonl file.
2) Generate literature queries.
3) Search PubMed for the top query.
4) Create the HTML report with embedded visualizations and literature context.

## Report Focus

- ATP binding dynamics and pocket geometry
- Consensus RMSF and DCCM clustering
- Comparative insights across pseudokinase holo structures

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain all per‑system metrics, statistics, and image paths.

**Reason:** Need the analysis data for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create prioritized PubMed queries based on the protein name, MD simulation context, and analysis methods.

**Reason:** Generate queries that target relevant literature for later searching.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "dihedral PCA",
    "ATP binding"
  ],
  "user_goal": "Compare ATP binding dynamics across 37 pseudokinase holo structures.",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve recent publications for the highest‑priority query.

**Reason:** Obtain a concise list of references to embed in the report.

**Parameters:**
```json
{
  "query": "{{GENERATE_LITERATURE_QUERIES_OUTPUT.queries['priority_1']}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report with embedded plots, key statistics, and literature citations.

**Reason:** Produce the final deliverable.

**Parameters:**
```json
{
  "analysis_data": "{{READ_ANALYSIS_SUMMARY_OUTPUT.data}}",
  "literature_refs": "{{SEARCH_PUBMED_OUTPUT.results}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

