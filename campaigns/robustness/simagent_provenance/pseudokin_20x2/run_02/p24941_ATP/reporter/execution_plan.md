# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The workflow requires parsing the per‑simulation analysis summary, optionally enriching the report with literature context, and finally generating a comprehensive HTML report with embedded plots and statistics. The steps use only the available tools and respect the directory conventions specified in the prompt.

## Overview

1. Read and parse `analysis/analysis_summary.jsonl`. 2. Generate PubMed queries that target the protein and the specific MD metrics. 3. Execute a PubMed search to gather recent literature references. 4. Create an HTML report that includes the analysis data, embedded images, key statistics, and literature citations.

## Report Focus

- Key descriptors of ATP binding and pocket dynamics
- Global protein flexibility and inter‑lobes communication

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the per‑simulation analysis results, statistics, and image paths from the JSONL file.

**Reason:** We need the analysis data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries

**Tool:** `generate_literature_queries`

**Description:** Create focused PubMed search queries based on the protein name and the MD metrics that were calculated.

**Reason:** These queries will drive the literature search and ensure relevance.

**Parameters:**
```json
{
  "analysis_types": [
    "COM distance",
    "orientation",
    "chi1 angles",
    "RMSF",
    "DCCM",
    "PCA dynamics"
  ],
  "user_goal": "Analyze the p24941_ATP holo complex",
  "protein_name": "p24941",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute a PubMed search using the highest‑priority query and collect recent articles for contextual information.

**Reason:** Providing up‑to‑date references will enrich the report.

**Parameters:**
```json
{
  "query": "{{priority_query_1}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds analysis images, displays key statistics, and lists literature citations.

**Reason:** This produces the final deliverable in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_summary}}",
  "literature_refs": "{{pubmed_results}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

