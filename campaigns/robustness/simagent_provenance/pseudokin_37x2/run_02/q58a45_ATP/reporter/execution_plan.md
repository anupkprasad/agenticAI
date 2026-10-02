# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl file already contains all per‑replica metrics, the averaged ten‑scalar feature vector, the Ward clustering output (dendrogram and heatmap image paths) and the robustly scaled heatmap.  Therefore the report can be produced in a single pass by (1) reading the summary, (2) generating an HTML report that embeds all the images, shows the key statistics cards, and (3) augmenting the report with a brief literature context.  No further data processing is required.

## Overview

1. Parse analysis_summary.jsonl to collect statistics and image file paths. 2. Search PubMed and bioRxiv for a small set of recent papers that discuss ATP binding to pseudokinases and the analysis methods used (RMSF, DCCM, PCA of torsions). 3. Use generate_html_report to create a single, self‑contained HTML report (report.html) that embeds all visualisations, shows key metrics, and includes the literature snippets.

## Report Focus

- ATP COM distance and orientation relative to the pocket axis
- Side‑chain χ₁ flexibility of pocket residues
- Consensus Cα RMSF and lobe‑to‑lobe correlated motion
- PCA of shared φ/ψ/χ₁ dynamics
- Hierarchical clustering of the ten‑scalar feature vector

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the per‑replica and averaged metrics, clustering images and any other plot paths from analysis_summary.jsonl.

**Reason:** All quantitative results and figure locations are stored here.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed/bioRxiv search terms that target ATP‑binding pseudokinases and the specific analysis methods used.

**Reason:** To retrieve up‑to‑date literature for contextual commentary.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "ATP binding",
    "pseudokinase"
  ],
  "user_goal": "Analyse ATP binding dynamics and conformational flexibility in the q58a45_ATP system.",
  "protein_name": "q58a45",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve the most recent 3–5 papers matching the first query.

**Reason:** Obtain peer‑reviewed literature relevant to ATP binding and MD analysis.

**Parameters:**
```json
{
  "query": "{{generated_query_1}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Search bioRxiv

**Tool:** `search_biorxiv`

**Description:** Retrieve the most recent 2–3 preprints matching the second query.

**Reason:** Capture cutting‑edge, unpublished studies that may offer complementary insights.

**Parameters:**
```json
{
  "query": "{{generated_query_2}}",
  "max_results": 3,
  "max_age_years": 2
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds all figures, displays key statistics, and includes literature excerpts.

**Reason:** Deliver the final visual and textual product.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_summary_json}}",
  "literature_refs": [
    "{{pubmed_results}}",
    "{{biorxiv_results}}"
  ],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

