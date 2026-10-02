# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report must summarize per‑system descriptors, clustering outcomes, and place the findings in a broader EGFR context. We therefore need to parse the generated analysis_summary.jsonl, pull the required image paths and statistics, retrieve recent EGFR‑related literature, and then ask the reporting tool to assemble a clean HTML document.

## Overview

The workflow reads the analysis summary, generates literature queries (targeting EGFR and the key analyses), fetches relevant PubMed entries, and finally creates a single, comprehensive report in the reporter directory.

## Report Focus

- ATP‑COM distance dynamics
- Consensus RMSF and DCCM patterns
- Clustering of the ten‑descriptor space
- EGFR functional context and literature

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load all per‑system metrics, statistics, and figure paths from the analysis summary file.

**Reason:** We need the full dataset to feed the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that target EGFR, MD simulations, and the specific analyses performed.

**Reason:** These queries will be used to retrieve the most relevant literature.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "RMSD",
    "dihedral PCA",
    "consensus DCCM"
  ],
  "user_goal": "Generate comprehensive analysis of ATP\u2011bound EGFR dynamics and cluster descriptor space",
  "protein_name": "EGFR",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Fetch up to five recent articles matching the highest‑priority query.

**Reason:** Provide concise, up‑to‑date context for EGFR dynamics.

**Parameters:**
```json
{
  "query": "EGFR ATP binding site dynamics MD",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, embedded‑image report summarizing the descriptors, clustering, and literature.

**Reason:** This produces the final deliverable required in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

