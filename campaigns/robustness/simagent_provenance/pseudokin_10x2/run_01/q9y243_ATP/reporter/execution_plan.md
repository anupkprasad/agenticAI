# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a comprehensive HTML report for a single‑replicate analysis of the ATP‑bound AKT3 system (q9y243_ATP). The analysis results (scalar descriptors, statistics and pre‑generated plots) are stored in the file `analysis/analysis_summary.jsonl`. The workflow therefore consists of: 1) parsing that file to obtain all numerical results and image paths; 2) enriching the report with relevant literature; 3) generating the final HTML report with embedded images and key statistics. No further MD or preprocessing is required, and we adhere to the tool constraints (no `working_dir` argument, use of `report.html` as the output filename).

## Overview

1. Read and parse the analysis summary. 2. Build literature queries focused on AKT3 ATP‑binding dynamics and the descriptors computed. 3. Query PubMed to retrieve recent, high‑impact papers. 4. Assemble the analysis data and literature references into a comprehensive report.

## Report Focus

- ATP COM distance to consensus pocket
- ATP orientation relative to pocket axis
- Pocket side‑chain χ1 dynamics
- Consensus‑mapped Cα RMSF
- N‑lobe vs C‑lobe DCCM
- Shared‑reference dihedral PCA scalar

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the `analysis/analysis_summary.jsonl` file to obtain numerical statistics, descriptor averages, and paths to the pre‑generated plot images.

**Reason:** We need all quantitative results and image locations for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Search Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed queries that target AKT3 ATP‑binding dynamics, the specific descriptors (RMSF, DCCM, dihedral PCA), and recent MD studies of AKT3 or related kinases.

**Reason:** Contextual literature will help interpret the computed metrics.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "dihedral PCA",
    "ATP binding"
  ],
  "user_goal": "Analysis & Reporting for q9y243_ATP (AKT3 holo)",
  "protein_name": "AKT3",
  "analysis_stats": {
    "RMSF": {
      "mean": 0.15,
      "max": 0.35
    },
    "DCCM": {
      "mean": 0.4,
      "max": 0.8
    }
  }
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the highest‑priority query returned by the literature query generator to retrieve up to 10 recent (≤ 5 yr) peer‑reviewed articles with abstracts.

**Reason:** We need concrete references to include in the report.

**Parameters:**
```json
{
  "query": "AKT3 ATP binding dynamics MD simulation",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report (`report.html`) that embeds all analysis plots, presents key statistics cards, and cites the PubMed references obtained. The report will have modern styling and a clear section for each descriptor.

**Reason:** This is the final deliverable required by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

