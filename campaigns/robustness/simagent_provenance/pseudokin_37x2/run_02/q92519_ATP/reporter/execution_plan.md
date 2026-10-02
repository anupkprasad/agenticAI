# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The task requires a single‑simulation HTML report that incorporates all analysis outputs stored in the JSONL file and optionally contextual literature. We first load the analysis data, then optionally generate PubMed queries to enrich the report with recent literature. Finally, we feed the parsed data into `generate_html_report` to produce a self‑contained, base64‑encoded HTML document with embedded plots and statistical cards.

## Overview

1️⃣ Read the analysis summary (JSONL). 2️⃣ (Optional) Build PubMed search queries for contextual literature. 3️⃣ Generate a comprehensive HTML report embedding all visualizations and key statistics.

## Report Focus

- Key statistical metrics for each analysis (mean, std, min, max)
- Visualization of ligand pocket dynamics
- Consensus RMSF and DCCM patterns
- Cluster dendrogram and feature heat‑map
- Literature context linking simulation findings to experimental insights

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to extract all per‑system metrics, statistics, and image paths.

**Reason:** We need the raw analysis results to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries based on the protein name, simulation context, and analysis methods to fetch relevant literature.

**Reason:** Provides structured queries for the subsequent PubMed search.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DCCM",
    "Torsion",
    "Dihedral PCA",
    "Contact Map",
    "Ligand Pocket Distance",
    "Consensus Metrics"
  ],
  "user_goal": "Perform per\u2011system analysis of protein\u2011ATP holo trajectories and report clustering results.",
  "protein_name": "pseudokinase ATP holo",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve abstracts and citations that match the generated queries.

**Reason:** To supply up‑to‑date literature context for the report.

**Parameters:**
```json
{
  "query": "pseudokinase ATP holo simulation RMSD",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report embedding all analysis images and statistics.

**Reason:** Produces the final deliverable expected by the user.

**Parameters:**
```json
{
  "analysis_data": "<placeholder for parsed analysis summary>",
  "literature_refs": "<placeholder for PubMed results>",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

