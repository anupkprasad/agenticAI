# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The workflow for a single‑simulation report only requires two core tools: (1) reading the pre‑generated analysis summary and (2) creating an HTML report from that data.  Because the user explicitly requested literature context, a lightweight literature search is added after parsing the summary.  The plan keeps the process deterministic, uses the available tools, and follows the file‑path conventions mandated in the prompt.

## Overview

1️⃣ Load analysis results from `analysis/analysis_summary.jsonl`. 2️⃣ (Optional) Build PubMed queries from the analysis types, fetch recent references, and gather their metadata. 3️⃣ Generate a comprehensive HTML report that embeds plots, displays key statistics, and incorporates the literature citations.

## Report Focus

- ATP‑binding pocket dynamics
- Consensus torsion PCA
- Protein RMSF & DCCM patterns

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing per‑replica metrics, aggregated statistics, and image file paths.

**Reason:** We need the analysis data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries based on the analysis types (e.g., RMSF, DCCM) and the protein name extracted from the summary metadata.

**Reason:** Prepare focused literature queries to retrieve contextually relevant papers.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "Torsion PCA",
    "Ligand\u2011Pocket Distance"
  ],
  "user_goal": "Per\u2011system analysis of ATP\u2011bound pseudokinase dynamics.",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the first high‑priority PubMed query and collect up to 10 recent references.

**Reason:** Obtain recent literature that discusses ATP‑bound pseudokinase dynamics.

**Parameters:**
```json
{
  "query": "pseudokinase ATP dynamics molecular dynamics",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds all analysis images, displays key statistics cards, and lists the literature references.

**Reason:** Produce the final deliverable in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

