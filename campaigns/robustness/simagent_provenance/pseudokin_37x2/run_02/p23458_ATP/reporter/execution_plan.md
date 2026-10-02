# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The reporter workflow requires first ingesting the per‑simulation analysis summary, optionally enriching the report with literature that contextualizes the computed descriptors, and finally generating a self‑contained HTML document that embeds all plots and key statistics.  The steps below are deterministic, use only the supplied tools, and obey the file‑path conventions mandated by the workspace layout.

## Overview

1. Load the JSONL analysis summary. 2. Create PubMed search queries that target pseudokinase dynamics, the specific descriptor methods, and the clustering hypothesis. 3. Retrieve the top PubMed abstracts. 4. Build a concise HTML report that lists the clustering results, key descriptor statistics, and the literature references.

## Report Focus

- Clustering of ATP binding dynamics across pseudokinase and active kinase holo complexes
- Distribution and variability of key descriptors (ATP COM distance, pocket χ₁, RMSF, DCCM, PCA entropy)
- Interpretation of cluster identities in light of functional annotations

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file that contains all per‑system descriptor statistics, dendrogram and heatmap image paths.

**Reason:** Load all analysis data that will feed the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Construct PubMed queries that focus on pseudokinase ATP binding, MD descriptor methods (RMSF, DCCM, PCA entropy), and clustering analysis.

**Reason:** Create search queries that are specific enough to retrieve relevant recent literature.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA entropy",
    "clustering"
  ],
  "user_goal": "Compute clustering of pseudokinase ATP holo complex descriptors and summarise the key statistical trends.",
  "protein_name": "pseudokinase",
  "analysis_stats": {
    "RMSF": {
      "mean": 2.5,
      "max": 5.0
    },
    "DCCM": {
      "mean": 0.3,
      "max": 0.7
    }
  }
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute PubMed searches for each query generated above and collect abstracts and citation information.

**Reason:** Obtain up to date scientific context for the descriptors and clustering.

**Parameters:**
```json
{
  "query": "{{query}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report embedding all analysis plots, statistics cards, and literature references.

**Reason:** Produce the final deliverable that will be stored in `/reporter/`.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_summary}}",
  "literature_refs": "{{pubmed_results}}",
  "report_type": "comprehensive",
  "output_file": "report.html",
  "enriched_prompt": "Generate a concise report summarising the clustering of ATP\u2011bound pseudokinase complexes, highlighting key descriptor statistics and contextualising findings with recent literature."
}
```

