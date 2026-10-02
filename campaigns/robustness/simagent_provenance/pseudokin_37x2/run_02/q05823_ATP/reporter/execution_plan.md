# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report must summarize the scalar descriptors, display the dendrogram and heat‑map, and provide literature context on pseudokinase vs active kinase behavior.  The analysis results are already stored in `analysis_summary.jsonl`.  We will parse this file, then query PubMed for recent literature that discusses the KAPCA pocket, consensus‑based metrics, and pseudokinase activity.  Finally, we will feed the parsed analysis data together with the literature references into `generate_html_report` to produce a self‑contained, professionally styled HTML file (`report.html`) in the `reporter/` directory.

## Overview

1. Parse analysis results
2. Generate PubMed search queries (protein‑specific + method‑specific)
3. Retrieve up to 5 recent PubMed abstracts
4. Build a reference list
5. Produce the final HTML report

## Report Focus

- Summary of simulation conditions and scalar descriptors
- Visualizations: dendrogram, heat‑map, and per‑descriptor plots
- Literature context on KAPCA pocket mapping and pseudokinase activation

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the per‑simulation analysis results and image paths from `analysis/analysis_summary.jsonl`.

**Reason:** Need the scalar descriptors, cluster plots, and metadata for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search strings that target the protein family, KAPCA pocket, and the scalar descriptors used.

**Reason:** To build focused, high‑quality PubMed queries.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP distance",
    "ATP orientation",
    "RMSF",
    "DCCM",
    "dihedral PCA entropy"
  ],
  "user_goal": "Summarize simulation conditions, list computed descriptors, and provide literature context on pseudokinase vs active kinase behavior.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Query PubMed with the generated queries and retrieve the most recent 5 relevant papers (abstracts included).

**Reason:** Obtain up‑to‑date literature to cite in the report.

**Parameters:**
```json
{
  "query": "\"pseudokinase\" AND \"ATP\" AND \"MD simulation\"",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Extract Literature References

**Tool:** `search_pubmed`

**Description:** Format the PubMed results into a list of citation objects suitable for the report.

**Reason:** Collect a second set of references that focus on activation mechanisms.

**Parameters:**
```json
{
  "query": "\"pseudokinase\" AND \"kinase activation\"",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds all analysis images, displays key statistics, and cites the literature.

**Reason:** Produce the final deliverable in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

