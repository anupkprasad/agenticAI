# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report must be built from the analysis results stored in analysis_summary.jsonl. We first read and parse this file to obtain all computed descriptors, statistics, and image paths. To provide a brief literature context, we query PubMed for recent studies on JAK2 ATP binding dynamics and MD simulation of kinase complexes. The retrieved references are then fed into the report generator. The generate_html_report tool automatically embeds the plot images and displays key statistics, so we only need to provide the parsed analysis data and the literature references.

## Overview

1️⃣ Read analysis results
2️⃣ Search PubMed for relevant literature
3️⃣ Generate a comprehensive HTML report with embedded plots, key statistics, and literature citations

## Report Focus

- ATP binding pocket dynamics in JAK2
- Domain‑level motions and correlation between N‑ and C‑lobes

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing all descriptor statistics and image paths for the two 200‑ns replicates.

**Reason:** Load the core analysis data that will drive the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve recent papers on JAK2 ATP binding and kinase MD simulations to provide literature context.

**Reason:** Provide up‑to‑date, relevant literature for the report.

**Parameters:**
```json
{
  "query": "JAK2 ATP binding MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional HTML report that embeds all analysis plots, displays key statistics, and cites the literature.

**Reason:** Produce the final deliverable.

**Parameters:**
```json
{
  "analysis_data": "{{read_analysis_summary.output}}",
  "literature_refs": "{{search_pubmed.output}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

