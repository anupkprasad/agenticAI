# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The single‑simulation report for p21860_ATP can be produced by parsing the locally stored analysis summary, optionally augmenting it with recent literature, and feeding the combined data into the `generate_html_report` tool. No further processing or external simulation steps are needed.

## Overview

1. Read the pre‑computed `analysis_summary.jsonl` file to obtain all descriptor values and embedded image paths. 2. Query PubMed for recent MD‑simulation studies of the same or homologous pseudokinase to provide context. 3. Call `generate_html_report`, supplying the parsed analysis data, the literature results, and specifying a single output file (`report.html`).

## Report Focus

- Summary of ATP‑pocket interaction metrics (distance, orientation)
- Structural flexibility of the consensus pocket (χ₁, RMSF)
- Cross‑domain coupling (DCCM correlation)
- Dihedral PCA‑based conformational spread

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains descriptor values, statistical summaries, and paths to any generated plots.

**Reason:** Load all analysis results needed for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Contextual Literature

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent peer‑reviewed articles describing MD simulations or functional studies of the p21860 pseudokinase (or its closest ortholog).

**Reason:** Provide literature context for the analysis and help interpret the derived descriptors.

**Parameters:**
```json
{
  "query": "p21860 pseudokinase molecular dynamics",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": null
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds the analysis plots, displays key statistical cards, and lists the literature references.

**Reason:** Deliver the final user‑facing document.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

