# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

Load analysis results, enrich with PubMed literature, and produce an embedded HTML report.

## Overview

The workflow parses the analysis summary, generates targeted literature queries, fetches relevant papers, aggregates references, and calls the HTML report generator with all data.

## Report Focus

- ATP binding pocket dynamics
- Global flexibility (RMSF, DCCM)
- Cluster analysis and k=4 cut
- Comparison of replicate statistics

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse analysis_summary.jsonl to obtain descriptor results, statistics, and image paths.

**Reason:** Need to load all analysis outputs.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create prioritized PubMed queries based on protein, methods, and hypothesis.

**Reason:** Generate focused search strings for relevant literature.

**Parameters:**
```json
{
  "analysis_types": [
    "COM distance",
    "Orientation",
    "Chi1",
    "RMSF",
    "DCCM",
    "Shared-reference dihedral PCA"
  ],
  "user_goal": "Analyze the two existing 200\u2011ns replicates for the CDK2\u2013ATP holo system (protein\u202f+\u202fligand, ions excluded) and compute the ten scalar dynamics descriptors defined in the user\u2019s list for each replicate, then average across replicates.",
  "protein_name": "CDK2",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute each generated query and retrieve up to 10 abstracts.

**Reason:** Collect recent literature supporting the analysis.

**Parameters:**
```json
{
  "query": "<generated query>",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": null
}
```

### Step 4: Compile References

**Tool:** `internal`

**Description:** Aggregate search results into a list of reference objects.

**Reason:** Prepare input for report generation.

**Parameters:**
```json
{}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report with embedded plots and literature.

**Reason:** Deliver the final scientific report.

**Parameters:**
```json
{
  "analysis_data": "<parsed analysis data from step 1>",
  "literature_refs": "<compiled references list>",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

