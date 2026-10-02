# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The workflow must ingest the already computed per‑system descriptors from the analysis_summary.jsonl file, optionally enrich the report with relevant literature, and output a single self‑contained HTML file named report.html in the reporter directory. We therefore first read the analysis summary, then generate a list of PubMed queries that match the analyses performed, search PubMed for recent literature, and finally build the report embedding the analysis data, plots, and literature references.

## Overview

1️⃣ Parse the analysis summary (contains descriptor values, statistics, and image file paths). 2️⃣ Build PubMed search queries based on the protein name, analysis types, and key statistics. 3️⃣ Retrieve literature results. 4️⃣ Generate a comprehensive HTML report that embeds all images and displays key statistics and literature citations.

## Report Focus

- ATP binding pocket dynamics across systems
- N‑lobe ↔ C‑lobe communication and dihedral PCA entropy

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all descriptor values, statistical summaries, and image paths for the 37 × 2 system runs.

**Reason:** We need the data to feed into the report and to create literature queries.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a prioritized set of PubMed search strings based on the analyses performed and the protein of interest.

**Reason:** These queries will guide the literature search to provide context for the computed descriptors.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "Pocket distance",
    "Ligand orientation",
    "Dihedral PCA entropy"
  ],
  "user_goal": "Generate a comprehensive analysis of ATP binding pocket dynamics and lobe\u2011lobe communication in pseudokinases across 37 systems.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve recent articles that match the generated queries.

**Reason:** To supply up‑to‑date literature references for inclusion in the report.

**Parameters:**
```json
{
  "query": "pseudokinase AND ATP binding pocket dynamics AND RMSF",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained report that embeds analysis images, displays key statistics, and lists the literature references obtained.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

