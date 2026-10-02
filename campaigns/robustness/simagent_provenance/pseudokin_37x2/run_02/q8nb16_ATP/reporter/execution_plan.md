# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis for the q8nb16_ATP system has already been completed by the Analysis Agent, and the results, statistics and paths to the visualisation files are stored in `analysis/analysis_summary.jsonl`. To produce the final deliverable for the user we only need to read this summary, extract the key metrics, embed the images and create a professional HTML report. The literature context will be added by querying PubMed for recent papers that discuss MD‑simulation studies of pseudokinases and ATP‑binding pocket dynamics. No additional calculations or re‑running of simulations are required.

## Overview

1. Read and parse the `analysis_summary.jsonl` file. 2. Build a set of literature queries focused on pseudokinase ATP binding and MD‑simulation analyses. 3. Use the parsed data and the literature references to generate a single `report.html` in the reporter directory. The report will include embedded figures, statistical tables, and concise interpretation.

## Report Focus

- ATP pocket dynamics and stability
- RMSF patterns across the pseudokinase structure
- Correlation between N‑ and C‑lobes (DCCM)
- Entropy of shared‑reference dihedral PCA
- Literature context of pseudokinase ATP binding

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis summary JSONL file to obtain all statistics, image paths and any metadata.

**Reason:** Need to load the results that were produced by the Analysis Agent.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that target recent literature on pseudokinase ATP‑binding dynamics and the specific analyses performed.

**Reason:** Provide a focused set of queries for the literature search step.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "ATP pocket distance",
    "dihedral PCA entropy"
  ],
  "user_goal": "Analyse ATP binding and dynamics in the q8nb16 pseudokinase system.",
  "protein_name": "q8nb16",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve recent articles that match the generated queries.

**Reason:** Collect contemporary studies that are relevant to the analyses.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding MD simulation",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all figures, presents key statistics in cards, and summarizes the literature context.

**Reason:** Produce the final user‑ready report.

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

