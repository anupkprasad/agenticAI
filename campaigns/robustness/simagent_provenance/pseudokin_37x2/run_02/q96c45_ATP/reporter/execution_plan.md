# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis workflow has already produced a JSONL file containing all per‑protein scalar descriptors, image paths, and computed statistics.  To produce a user‑friendly scientific report, we first load this summary, optionally enrich the context with recent literature, and then feed both the numerical results and the literature references into the `generate_html_report` tool, which automatically embeds images, adds key statistics cards, and creates a clean, professional layout.

## Overview

The plan will:
1. Load the analysis summary.
2. Generate PubMed query strings tailored to the proteins and the analysis types performed.
3. Retrieve relevant literature abstracts.
4. Produce a comprehensive HTML report that includes visualizations, statistics, and literature context.

## Report Focus

- Summary of the ten scalar descriptors per protein
- Cluster interpretation with Ward dendrogram and k=4 heatmap
- Literature context linking ATP‑binding dynamics to pseudokinase function

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain per‑protein metrics, image file paths, and any metadata such as protein identifiers.

**Reason:** We need the numerical results and image references to build the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries based on the proteins analysed, the specific descriptors (ATP COM distance, orientation, χ1, RMSF, DCCM, dihedral‑PCA entropy), and the user’s goal.  The queries will be used to fetch recent studies that discuss similar proteins or analysis methods.

**Reason:** Structured queries will target the most relevant recent literature for each analysis type.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "pocket \u03c71",
    "C\u03b1 RMSF",
    "DCCM",
    "dihedral\u2011PCA entropy"
  ],
  "user_goal": "For each of the 37 ATP\u2011holo trajectories, compute descriptors, map pockets, cluster, and report literature context.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the generated PubMed queries and retrieve article metadata, abstracts, and citations.

**Reason:** Gather up‑to‑date scholarly context for inclusion in the report.

**Parameters:**
```json
{
  "query": "",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all images (converted to base64), displays key statistics cards, and incorporates literature references.  The report will be stored as `report.html` in the reporter directory.

**Reason:** This is the final deliverable that the user expects.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

