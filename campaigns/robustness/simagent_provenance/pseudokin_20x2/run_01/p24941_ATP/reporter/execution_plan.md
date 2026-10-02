# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The workflow requires the analysis results for the two CDK2/ATP trajectories, contextual literature, and an integrated HTML report. We first parse the analysis_summary.jsonl file, then create targeted PubMed queries that capture both the protein of interest (CDK2) and the specific MD-derived descriptors. We retrieve the most relevant literature, combine it with the analysis data, and finally generate a self‑contained report with embedded plots and summary cards.

## Overview

1. Load analysis data from the JSONL file. 2. Generate PubMed search queries based on the analysis types and user goal. 3. Execute the PubMed search to collect recent, relevant articles. 4. Feed the analysis data and literature references into the report generator to produce a comprehensive HTML file.

## Report Focus

- Quantitative comparison of ATP binding dynamics across two replicas
- Structural flexibility of the active site pocket (χ1, RMSF)
- Correlation of global motions (DCCM, PCA) with ATP positioning

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the /home/akp66103/workspace/.../analysis/analysis_summary.jsonl file to obtain all scalar metrics, mean/SD values, and image paths for the two 200 ns trajectories.

**Reason:** We need the numerical values and figure locations to build the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a set of PubMed search queries that prioritise the protein (CDK2), the MD simulation context, and the specific descriptors (ATP COM distance/angle, pocket χ1, RMSF, DCCM, PCA).

**Reason:** We need focused queries to retrieve the most relevant literature for the specific analysis methods.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "COM distance",
    "torsion"
  ],
  "user_goal": "Analyze dynamic descriptors for CDK2 holo and contextualise with literature",
  "protein_name": "CDK2",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the generated queries and retrieve abstracts and citations for the most recent papers.

**Reason:** Collect up-to-date scientific context that relates the observed dynamics to known CDK2 behaviour.

**Parameters:**
```json
{
  "query": "CDK2 ATP MD simulation",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Search PubMed (additional)

**Tool:** `search_pubmed`

**Description:** Execute a second PubMed search for the specific analysis methods to capture methodological references.

**Reason:** Ensure methodological context is represented.

**Parameters:**
```json
{
  "query": "CDK2 RMSF analysis MD",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all plots, displays key statistics, and includes a literature section summarising the retrieved papers.

**Reason:** Produce the final user deliverable in the required format.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

