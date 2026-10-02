# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis summary contains all computed scalar descriptors and image paths. To generate a complete scientific report we need to (1) load this data, (2) enrich it with recent literature on the KAPCA ATP‑holo complex, and (3) produce a styled HTML report that embeds the time‑series plots and summarizes the key statistics. This workflow uses the provided tools in the order that respects data dependencies and ensures that all required inputs are available for the final report generation.

## Overview

1️⃣ Load analysis results from `analysis/analysis_summary.jsonl`. 2️⃣ Generate targeted PubMed queries for KAPCA–ATP and the analyses performed. 3️⃣ Retrieve up to five recent references per query. 4️⃣ Consolidate the references and feed them with the analysis data into `generate_html_report` to create `report.html` in the reporter output directory.

## Report Focus

- ATP binding pocket dynamics in the KAPCA holo complex
- Inter‑lobe communication and conformational flexibility
- Correlation of COM metrics with side‑chain torsion sampling

## Execution Steps (6 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing per‑frame descriptors, statistics, and image file paths.

**Reason:** We need the full set of computed metrics and plot paths to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries prioritizing the protein (KAPCA) and the MD‑simulation analysis methods.

**Reason:** Automated query generation ensures that literature searches are focused on the relevant protein and analysis techniques.

**Parameters:**
```json
{
  "analysis_types": [
    "COM distance",
    "COM orientation",
    "Pocket chi1",
    "C\u03b1 RMSF",
    "DCCM correlation",
    "PCA scalar"
  ],
  "user_goal": "Generate an analysis and reporter for the P17612 holo (ATP) system and provide literature context.",
  "protein_name": "KAPCA"
}
```

### Step 3: Search PubMed – Query 1

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent publications for the highest‑priority query.

**Reason:** We want recent, high‑impact literature that discusses KAPCA, ATP binding, or similar pseudokinase simulations.

**Parameters:**
```json
{
  "query": "{{generated_queries.priority_1}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Search PubMed – Query 2

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent publications for the second‑priority query.

**Reason:** A second query broadens the literature base without overwhelming the report.

**Parameters:**
```json
{
  "query": "{{generated_queries.priority_2}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 5: Aggregate Literature References

**Tool:** `aggregate_references`

**Description:** Combine the PubMed search results into a single list of reference objects suitable for the report.

**Reason:** The report generator expects a flattened list of citations.

**Parameters:**
```json
{
  "search_results": [
    "{{search_pubmed_query1.output}}",
    "{{search_pubmed_query2.output}}"
  ]
}
```

### Step 6: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report embedding all plots, statistics, and literature references.

**Reason:** This is the final deliverable for inclusion in the comparative study.

**Parameters:**
```json
{
  "analysis_data": "{{read_analysis_summary.output}}",
  "literature_refs": "{{aggregate_references.output}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

