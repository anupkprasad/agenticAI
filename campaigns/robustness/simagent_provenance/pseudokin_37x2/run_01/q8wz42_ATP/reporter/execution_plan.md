# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a concise HTML report that consolidates all analysis metrics from the 37 protein‑ATP holo structures. The report must embed all visualisations, display key statistics, and provide a brief literature context that compares pseudokinases to active kinases. The workflow therefore starts by reading the pre‑generated analysis summary, then (optionally) retrieves recent literature to contextualise the findings, and finally generates the report using the supplied analysis data and literature references.

## Overview

1. Load the analysis results from `analysis/analysis_summary.jsonl`. 2. Create PubMed search queries tailored to kinase–MD and pseudokinase literature, perform searches, and collect the top references. 3. Generate a comprehensive HTML report (`report.html`) that embeds the analysis plots, displays statistics cards, and inserts the literature citations.

## Report Focus

- Comparison of ATP‑binding dynamics between pseudokinases and active kinases
- Clustering of systems based on aggregated descriptors

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain all analysis metrics, statistics, and image paths.

**Reason:** We need the raw analysis data to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Search Queries

**Tool:** `generate_literature_queries`

**Description:** Construct PubMed search queries that focus on kinase MD simulations, pseudokinase structure–function, and the specific descriptors used in the analysis.

**Reason:** To ensure the literature search is relevant and focused.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "RMSF",
    "DCCM",
    "dihedral\u2011PCA entropy"
  ],
  "user_goal": "Use the already\u2011produced 200\u2011ns trajectories (rep01 and rep02) for all 37 protein\u2011ATP holo structures. For each system, compute per\u2011replicate and averaged metrics ... and compile a concise HTML report in the reporter directory that presents the clustering, key descriptor values, and brief literature context for the pseudokinase vs. active kinase comparison.",
  "protein_name": "",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the top two queries returned by the literature query generator to retrieve recent studies on kinase MD simulations and pseudokinase structural dynamics.

**Reason:** Obtain up‑to‑date references for contextualizing the analysis results.

**Parameters:**
```json
{
  "query": "${generated_queries['priority_1']}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Search PubMed (second query)

**Tool:** `search_pubmed`

**Description:** Execute the second top query to capture additional literature.

**Reason:** Broadening the reference set ensures comprehensive coverage.

**Parameters:**
```json
{
  "query": "${generated_queries['priority_2']}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report embedding all analysis images, key statistics, and literature citations.

**Reason:** The final deliverable must be a polished, self‑contained HTML file.

**Parameters:**
```json
{
  "analysis_data": "${analysis_summary}",
  "literature_refs": "${merged_pubmed_results}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

