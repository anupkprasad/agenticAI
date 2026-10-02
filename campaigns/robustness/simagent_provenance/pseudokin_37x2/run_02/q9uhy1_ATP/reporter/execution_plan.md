# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report generation workflow requires three core components: (1) ingesting the pre‑computed analysis results, (2) augmenting the narrative with up‑to‑date literature context, and (3) synthesising these into a cohesive, richly‑formatted HTML document.  The analysis_summary.jsonl file contains all scalar descriptors and image paths; this file is read first.  A brief literature query set is generated based on the descriptor types and the overarching research question, followed by PubMed searches to gather relevant references.  Finally, the `generate_html_report` tool is invoked, passing both the parsed analysis data and the curated literature list.  All intermediate artefacts (e.g., literature hits) are stored in memory; only the final report is written to the reporter directory as `report.html`.

## Overview

1. Read the analysis summary (200 ns trajectories, 37 systems). 2. Create targeted literature queries (protein‑ATP dynamics, RMSF, DCCM, PCA). 3. Retrieve recent PubMed articles for each query. 4. Generate a comprehensive HTML report with embedded plots, statistics cards, and literature context.

## Report Focus

- Trajectory‑level descriptor statistics (mean, σ, IQR)
- Cluster assignments and dendrogram visualisation
- Key functional insights (e.g., ATP binding mode shifts, pocket flexibility)
- Literature linkage to observed dynamical behaviours

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis/analysis_summary.jsonl` file to obtain per‑system descriptors and image paths.

**Reason:** Load all analysis results required for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Produce a set of PubMed search queries tailored to the protein context and the specific analyses performed.

**Reason:** Create focused queries that balance protein relevance, analysis method, and recent literature.

**Parameters:**
```json
{
  "analysis_types": [
    "COM distance",
    "Orientation",
    "Pocket chi1",
    "RMSF",
    "DCCM",
    "PCA"
  ],
  "user_goal": "Perform full\u2011trajectory analysis for 37 pseudokinase\u2011ATP holo systems and generate a robust clustering and visual summary.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute PubMed searches for each query returned by `generate_literature_queries` and collect the resulting references.

**Reason:** Obtain up‑to‑date, peer‑reviewed references to contextualise the findings.

**Parameters:**
```json
{
  "query": "{{queries[0]}}",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML document incorporating all analysis visuals, statistics, and literature citations.

**Reason:** Deliver the final, publication‑ready report.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_summary}}",
  "literature_refs": "{{literature_hits}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

