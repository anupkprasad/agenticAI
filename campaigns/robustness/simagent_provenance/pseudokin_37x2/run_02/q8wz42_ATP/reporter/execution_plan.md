# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The reporter only needs to transform the pre‑computed analysis results stored in the JSONL file into a polished, self‑contained HTML report.  The analysis data already contains all metric values and the file paths of the plots that should be embedded.  A short literature search on MD‑based studies of ATP‑binding pseudokinases will provide context for the findings.  No other external data or calculations are required.

## Overview

1️⃣ Read the `analysis_summary.jsonl` file.
2️⃣ Run a PubMed search for recent MD studies of ATP‑binding pseudokinases.
3️⃣ Generate a comprehensive HTML report that embeds all images, highlights key statistics, and cites the retrieved literature.

## Report Focus

- Quantitative descriptors of ATP binding pocket dynamics
- Comparison of per‑replica versus averaged metrics
- Placement of this system within the broader context of pseudokinase MD studies

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file located in the analysis directory.

**Reason:** Load the full set of per‑replica and aggregated metrics, plus the image paths, needed for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Literature Search

**Tool:** `search_pubmed`

**Description:** Search PubMed for recent MD simulation studies of ATP‑binding pseudokinases to provide contextual background.

**Reason:** Gather up‑to‑date, relevant literature that can be cited in the report’s discussion section.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding site molecular dynamics simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML file that embeds all analysis plots, displays key statistics in cards, and lists the literature references.

**Reason:** Produce the final deliverable that can be viewed in a web browser.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

