# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report requires a single HTML page that contains all the visualisations and key statistics extracted from the analysis_summary.jsonl file.  We therefore first read the summary, then (optionally) retrieve recent literature that relates the analysis methods and the pseudokinase systems.  Finally we call generate_html_report, passing the parsed analysis data together with the literature references and a short, system‑agnostic final impression.  No other tools are needed because all image paths are already embedded by the report generator.

## Overview

1️⃣ Read the analysis summary. 2️⃣ Build PubMed queries that target the pseudokinase MD analysis and the descriptors used. 3️⃣ Fetch a few recent papers. 4️⃣ Generate a comprehensive HTML report with embedded plots, statistics cards, and literature context.

## Report Focus

- Comparative dynamics of ATP binding across 20 pseudokinase holo systems
- Clustering of descriptor space and identification of four dynamic sub‑groups

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all scalar descriptors and image file paths for the 20 protein‑ATP systems.

**Reason:** Load the full set of analysis results that will populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a set of PubMed search strings that focus on pseudokinase MD studies, descriptor‑based analyses (RMSF, DCCM, PCA, pocket metrics) and the hypothesis of comparing 20 holo systems.

**Reason:** Provide targeted queries that will return recent, high‑impact literature.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "pocket metrics",
    "ATP binding"
  ],
  "user_goal": "Analysis & Reporting Goal: compare the dynamics of 20 pseudokinase\u2013ATP holo systems and summarise clustering results.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the top PubMed query returned in the previous step to collect a small set of recent articles.

**Reason:** Retrieve concrete literature to cite in the report.

**Parameters:**
```json
{
  "query": "pseudokinase molecular dynamics RMSF DCCM ATP binding",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a single comprehensive report (report.html) that embeds all analysis plots, displays key statistics, and includes a literature summary.

**Reason:** Produce the final deliverable that will be stored in /reporter/report.html.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

