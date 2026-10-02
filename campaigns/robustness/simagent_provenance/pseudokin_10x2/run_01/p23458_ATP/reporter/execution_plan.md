# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The per‑simulation report requires only the analysis summary and the generated visualizations. We first parse the JSONL file to obtain all metrics, image paths, and statistical summaries. Optionally, we can enrich the report with concise literature context by formulating PubMed queries and fetching the most relevant abstracts. Finally, the `generate_html_report` tool stitches the data and images into a self‑contained HTML file. No additional directories or combined‑report tools are needed for this single‑simulation workflow.

## Overview

1. Load analysis results. 2. (Optional) Search PubMed for short contextual references. 3. Build a comprehensive HTML report embedding images, statistics cards, and literature snippets.

## Report Focus

- Per‑system scalar dynamics descriptors (mean & SD)
- Robust heatmap of features
- Ward hierarchical clustering dendrogram
- Literature context for each kinase

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the per‑simulation analysis_summary.jsonl to extract metrics, image paths, and statistical summaries.

**Reason:** We need the full set of scalar descriptors and plot paths for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Context (Optional)

**Tool:** `generate_literature_queries`

**Description:** Formulate PubMed search queries based on the protein name and the analyses performed, then fetch a few recent abstracts.

**Reason:** Providing a brief literature backdrop adds value to the report and helps contextualize the findings.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "RMSF",
    "DCCM"
  ],
  "user_goal": "Analyze holo kinase dynamics",
  "protein_name": "ExampleKinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve the top PubMed entries for the generated queries.

**Reason:** Obtain actual reference data to embed in the report.

**Parameters:**
```json
{
  "query": "ExampleKinase ATP dynamics simulation",
  "max_results": 3,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML file that includes embedded visualizations, statistical cards, and literature references.

**Reason:** This is the final deliverable that satisfies the user’s reporting requirement.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

