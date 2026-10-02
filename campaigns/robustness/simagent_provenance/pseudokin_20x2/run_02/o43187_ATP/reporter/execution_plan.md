# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis summary already contains all scalar descriptors, statistics, and image paths required for the report. By parsing this JSONL we can feed the data directly into the report generator. Literature context is valuable for interpreting the clustering results, so we perform a focused PubMed search for recent kinase‑ATP dynamics studies and pseudokinase MD work. The final HTML report aggregates the visualizations, key statistics, and literature citations in a clean, professional layout.

## Overview

1️⃣ Read the per‑simulation analysis summary.
2️⃣ Build a concise set of PubMed queries that capture recent MD and kinetic literature on ATP‑bound kinases/pseudokinases.
3️⃣ Retrieve the top references for each query.
4️⃣ Generate a single `report.html` that embeds all plots, displays the feature‑heatmap and dendrogram, and lists the literature citations.

## Report Focus

- Ward‑hierarchical clustering of the 10‑descriptor feature set
- Interpretation of the k=4 dendrogram cut
- Comparative dynamics of ATP pocket vs. side‑chain χ₁ and RMSF across kinases/pseudokinases

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load all per‑simulation statistics, images, and descriptor values from `analysis/analysis_summary.jsonl`.

**Reason:** We need the numeric data and image paths to feed the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a small set of PubMed search strings that target recent MD studies of kinase/ATP binding pockets and pseudokinase dynamics.

**Reason:** These queries will be used to fetch context‑relevant literature.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA"
  ],
  "user_goal": "compare ATP\u2011bound kinase dynamics across 20 holo systems and interpret clustering results",
  "protein_name": "kinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** For each generated query, retrieve up to 5 recent PubMed records (abstracts, titles, authors).

**Reason:** Collect recent peer‑reviewed studies that discuss similar analyses.

**Parameters:**
```json
{
  "query": "kinase ATP binding pocket dynamics MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report (`report.html`) that embeds all visualizations, displays key statistics, and lists the literature citations.

**Reason:** This is the final deliverable that satisfies the user goal.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

