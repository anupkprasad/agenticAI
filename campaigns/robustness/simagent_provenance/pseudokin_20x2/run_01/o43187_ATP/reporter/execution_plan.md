# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that presents all analysis results from the analysis_summary.jsonl file, embeds the associated images, and optionally adds literature context. The report should be generated with `generate_html_report`. The workflow therefore consists of reading the analysis summary, optionally retrieving relevant literature, and then invoking the report generator. The analysis_summary file already contains all required statistics and image paths, so no additional calculations are needed. Literature queries are generated based on the analysis types present in the summary and the user goal, then PubMed and bioRxiv are searched for recent, relevant references. The final HTML report will include embedded plots, key statistic cards, and literature citations.

## Overview

1. Load analysis_summary.jsonl. 2. (Optional) Generate literature queries, search PubMed/bioRxiv. 3. Create the comprehensive HTML report, embedding all figures and stats.

## Report Focus

- Consensus pocket residues and ATP proximity
- Statistical descriptors of ATP orientation and pocket dynamics
- RMSF, DCCM, and PCA insights across the two replicates
- Literature context for IRAK2 ATP binding and dynamics

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all metrics and image file paths.

**Reason:** All analysis results and figure locations are stored in this file.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed/bioRxiv search queries that target the protein (IRAK2) and the specific analysis methods (e.g., ATP pocket dynamics, RMSF, DCCM).

**Reason:** Providing context from recent literature enhances the report.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP pocket distance",
    "orientation",
    "\u03c7\u2081",
    "RMSF",
    "DCCM",
    "PCA"
  ],
  "user_goal": "Analyze the holo IRAK2 (o43187) with ATP and compute consensus pocket metrics over two replicates, then average the descriptors.",
  "protein_name": "IRAK2",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve up to 5 recent PubMed articles for each generated query.

**Reason:** Collect peer‑reviewed references relevant to the analysis.

**Parameters:**
```json
{
  "query": "IRAK2 ATP pocket dynamics PubMed",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Search bioRxiv

**Tool:** `search_biorxiv`

**Description:** Retrieve up to 3 preprints that discuss IRAK2 or related kinase dynamics.

**Reason:** Include the latest preprints for a comprehensive literature context.

**Parameters:**
```json
{
  "query": "IRAK2 ATP dynamics",
  "max_results": 3,
  "max_age_years": 5
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, comprehensive HTML report that embeds all images, displays key statistics, and cites the gathered literature.

**Reason:** This tool builds the final deliverable with embedded figures and literature references.

**Parameters:**
```json
{
  "analysis_data": "${Read Analysis Summary.output}",
  "literature_refs": [
    "${Search PubMed.output}",
    "${Search bioRxiv.output}"
  ],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

