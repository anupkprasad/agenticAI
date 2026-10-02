# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that includes all plots, summary statistics, and contextual literature. The analysis results are already stored in `analysis/analysis_summary.jsonl`, which contains the scalar descriptors, images and metadata. We therefore: 1) read and parse the summary, 2) construct relevant PubMed queries to provide background on JAK3, ATP binding, and the specific analyses (distance, orientation, χ₁, RMSF, DCCM, dihedral PCA), 3) perform a PubMed search, 4) feed the parsed data and literature references into `generate_html_report` to produce a self‑contained `report.html` in the reporter directory.

## Overview

Read analysis summary → Search literature → Generate HTML report with embedded plots and statistics.

## Report Focus

- ATP–JAK3 binding dynamics
- Comparison of scalar descriptors to literature benchmarks

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain analysis metrics, image paths and metadata.

**Reason:** Need to load all analysis results for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed queries that target JAK3, ATP binding, and the analysis methods used.

**Reason:** To retrieve relevant recent literature for contextual discussion.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP binding site",
    "ATP COM distance",
    "ATP orientation",
    "chi1 torsion analysis",
    "RMSF",
    "DCCM",
    "dihedral PCA"
  ],
  "user_goal": "Analyse JAK3 ATP binding dynamics and compare to literature.",
  "protein_name": "JAK3",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Query PubMed with the generated queries to obtain article metadata.

**Reason:** Gather recent studies that discuss JAK3 ATP interactions and MD analysis.

**Parameters:**
```json
{
  "query": "JAK3 AND ATP AND \"binding site\" AND \"molecular dynamics\"",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report embedding all plots, statistics and literature references.

**Reason:** Produce the final deliverable for the user.

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

