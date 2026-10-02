# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report requires only a single‑simulation, per‑system summary.  The analysis artifacts are already produced in `analysis/analysis_summary.jsonl` and the image paths are embedded in that file.  A straightforward two‑step workflow—load the summary, feed it into `generate_html_report`—suffices to produce the required `report.html`.  Optionally, a literature search can enrich the context, but the primary deliverable is the HTML file with embedded visualisations and statistics.

## Overview

1. Parse the per‑system analysis summary. 2. (Optional) Run a focused PubMed search for recent MD‑simulation studies on the same pseudokinase family. 3. Create a comprehensive HTML report that embeds all plots and key statistics, and optionally lists literature references.

## Report Focus

- Dynamics of the ATP‑binding pocket relative to the KAPCA reference
- Quantitative comparison of scalar descriptors across the two 200‑ns replicates
- Hierarchical clustering of the 20 holo kinase–ATP complexes

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file located in the `analysis/` directory.  This file contains the computed scalar descriptors, trajectory plots, and any intermediate metrics that were produced by the analysis agent.

**Reason:** We need the raw analysis data and image paths to build the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries (Optional)

**Tool:** `generate_literature_queries`

**Description:** Create a set of PubMed search queries that focus on pseudokinase MD simulations and the specific analytical methods used (e.g., RMSF, PCA, DCCM).  The queries are then executed to retrieve up to 10 relevant recent papers.

**Reason:** Adding literature references enhances the report’s scientific value.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "RMSD"
  ],
  "user_goal": "Provide context for the ATP\u2011binding pocket dynamics in pseudokinases",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the generated PubMed queries and collect metadata and abstracts for the top hits.

**Reason:** Retrieve recent literature to contextualise the findings.

**Parameters:**
```json
{
  "query": "",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML file (`report.html`) that embeds all visualisations from the summary, displays key statistical cards, and optionally lists the literature references obtained in the previous step.

**Reason:** Produce the final deliverable – a professional, self‑contained HTML report.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": {},
  "final_impression": ""
}
```

