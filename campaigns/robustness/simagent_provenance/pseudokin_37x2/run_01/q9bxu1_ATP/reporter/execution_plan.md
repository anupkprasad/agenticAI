# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl contains all computed descriptors, statistics and image paths for the single‑simulation run.  We first parse this file to extract the quantitative results and references to any plot files.  Since the user explicitly asked for literature context, we generate targeted PubMed queries based on the analysis types and the protein of interest (pseudokinase).  The generated queries are used to fetch the most relevant recent papers (≤ 5 years).  Finally, the `generate_html_report` tool is invoked to produce a self‑contained, visually rich HTML report named `report.html` in the reporter’s working directory.  All tool calls are minimal and deterministic; no preprocessing or new simulations are performed.

## Overview

The workflow parses the pre‑generated analysis summary, retrieves supporting literature, and creates a comprehensive, per‑simulation HTML report with embedded figures and key statistics.

## Report Focus

- Key structural descriptors (distance, χ1, RMSF, DCCM, PCA entropy)
- Clustering interpretation in the context of known pseudokinase dynamics

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain all descriptors, statistics, and image paths.

**Reason:** Need to load the analysis results for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries

**Tool:** `generate_literature_queries`

**Description:** Create targeted PubMed search queries using the analysis types and protein name.

**Reason:** Build context‑aware literature search queries.

**Parameters:**
```json
{
  "analysis_types": [
    "Ligand\u2011pocket distance",
    "Pocket side\u2011chain \u03c71",
    "Consensus\u2011mapped C\u03b1 RMSF",
    "N\u2011lobe \u2194 C\u2011lobe DCCM",
    "Dihedral PCA entropy"
  ],
  "user_goal": "Per\u2011system analysis of pseudokinase holo trajectories to interpret clustering.",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve the top 5 recent papers for each query.

**Reason:** Obtain up‑to‑date references to include in the report.

**Parameters:**
```json
{
  "query": "{{queries.1}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, embedded report with figures, statistics and literature context.

**Reason:** Produce the final deliverable.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_summary}}",
  "literature_refs": "{{pubmed_results}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

