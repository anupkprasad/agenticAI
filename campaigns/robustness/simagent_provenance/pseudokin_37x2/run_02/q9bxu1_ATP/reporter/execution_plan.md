# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl file already contains all computed descriptors, statistical summaries, and image paths for the 37 protein‑ATP holo systems. Reading this file gives us a structured dictionary that the reporter can directly use to embed images and statistics. The only remaining step is to produce a single, comprehensive HTML report that presents the dendrogram, heatmap, clustering results, and key numerical metrics, along with literature context for pseudokinase versus active kinase behavior.

## Overview

1. Load the analysis summary. 2. Generate a concise HTML report embedding all visuals and key statistics. 3. Optionally include literature references on pseudokinase function and MD‑based analyses.

## Report Focus

- Comparison of ATP‑binding pocket metrics across 37 pseudokinase systems
- Hierarchical clustering (Ward) and dendrogram interpretation
- Consensus pocket mapping via MAFFT MSA
- Statistical summaries (mean, std, IQR) for all scalar descriptors
- Literature context on pseudokinase activity vs. active kinase regulation

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain a dictionary of all analysis results, statistical metrics, and image paths.

**Reason:** Need the raw analysis data for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, self‑contained HTML report that embeds the dendrogram, heatmap, clustering results, and key metrics for each descriptor, and adds literature context about pseudokinase versus active kinase function.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

