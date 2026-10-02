# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already produced a comprehensive analysis_summary.jsonl file containing all per‑system metrics, statistics and image paths. The only remaining task is to parse that file, extract the data, and generate a single HTML report that embeds the visualisations and highlights the key statistics. No additional computational analysis is required, and literature context is optional; a lightweight set of PubMed queries can be added if desired.

## Overview

1) Read the analysis_summary.jsonl file to obtain a structured dictionary of all results. 2) Pass the parsed data to generate_html_report to create a self‑contained, base64‑embedded HTML report in the reporter directory. 3) Optionally perform a quick PubMed search for background literature on ATP‑bound pseudokinases and the specific analysis methods used.

## Report Focus

- ATP binding pocket dynamics and COM distance statistics
- Ligand orientation and pocket χ1 distribution
- Consensus‑mapped Cα RMSF patterns
- Domain coupling (N‑lobe ↔ C‑lobe DCCM)
- Clustering of holo complexes by Ward hierarchical clustering

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the analysis_summary.jsonl file that contains all scalar descriptors, images and metadata.

**Reason:** Need the structured analysis data for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all images, displays key statistics, and provides a clear visual hierarchy.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

