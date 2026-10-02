# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl file already contains all numeric descriptors, statistics and the paths to the generated images. We only need to parse this file, optionally enrich it with a few literature references, and feed the data straight into the generate_html_report tool, which will embed the images, render statistics cards and produce a polished, self‑contained HTML page. No additional processing of trajectories is required.

## Overview

1️⃣ Load the analysis summary. 2️⃣ (Optional) Perform a quick PubMed search for contextual literature. 3️⃣ Generate a comprehensive HTML report that includes all figures and key statistics.

## Report Focus

- ATP binding pocket dynamics across 20 pseudokinases
- Consensus pocket flexibility and lobe coordination
- Cluster‑based grouping of dynamic behaviour (Ward, k=4)

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain a dictionary of analysis results, statistics, and image paths.

**Reason:** We need the raw analysis data to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a small set of PubMed queries focused on ATP‑binding pseudokinases and MD‑simulation analysis.

**Reason:** To produce context‑specific literature references that can be embedded in the report.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "RMSF",
    "DCCM",
    "pocket \u03c71"
  ],
  "user_goal": "Analyze ATP binding dynamics and pocket flexibility in pseudokinases.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute a PubMed search using the top query from the previous step.

**Reason:** Collect recent, relevant literature to support the analysis.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding site dynamics simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a self‑contained, comprehensive HTML report that embeds images, shows key statistics, and lists literature references.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": "<placeholder_for_output_of_read_analysis_summary>",
  "literature_refs": "<placeholder_for_output_of_search_pubmed>",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

