# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The goal is to produce a single, self‑contained HTML report that summarizes the per‑system metrics and places them in a broader scientific context. The workflow will read the existing `analysis_summary.jsonl` file, pull the relevant images and statistics, perform a targeted PubMed search to collect recent literature on pseudokinase ATP binding dynamics, and then invoke `generate_html_report` to weave the data, plots, and literature references into a polished document.

## Overview

1️⃣ Read the analysis summary (metrics + image paths). 2️⃣ Query PubMed for recent papers on pseudokinase ATP dynamics. 3️⃣ Generate a comprehensive HTML report embedding the data, visualizations, key statistics cards, and literature citations.

## Report Focus

- ATP binding pocket distance & orientation
- Side‑chain torsional distributions
- Cα RMSF and lobe correlation
- Dihedral PCA entropy
- Clustering insights (k=4 suggestion)

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse `analysis_summary.jsonl` to extract metrics, statistics, and image file paths for the 37 systems.

**Reason:** Load all analysis outputs that will populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve recent literature relevant to pseudokinase ATP binding dynamics to provide context for the metrics.

**Reason:** Provide up‑to‑date references that explain the significance of the computed descriptors.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding dynamics",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML document that embeds the analysis images, displays key statistics cards, and lists the PubMed citations.

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

