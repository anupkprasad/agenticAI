# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The workflow requires only a single‑simulation report. The analysis_summary.jsonl contains all computed descriptors, statistical summaries and image paths that the report generator will embed. No additional processing or averaging is needed beyond what the analysis agent already produced. We will first read that summary, then hand the parsed data to generate_html_report to produce a self‑contained HTML document with embedded visuals, statistics cards and literature context (if available).

## Overview

1️⃣ Parse the `analysis_summary.jsonl` file. 2️⃣ Pass the parsed data to `generate_html_report` to create a comprehensive HTML report named `report.html` inside the reporter directory.

## Report Focus

- Scalar descriptor averages and standard deviations across replicates
- Pocket χ1 torsion statistics for residues within 15 Å of ATP
- Trajectory visualizations (distance, RMSF, DCCM, PCA scalar)
- Ward hierarchical clustering dendrogram and heat‑map
- Literature context linking ATP binding dynamics and pseudokinase function

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the JSONL file that contains all descriptor values, aggregated statistics, and image file references.

**Reason:** The report generator needs the full set of metrics and image paths to embed them in the HTML.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, self‑contained HTML report that embeds all trajectory plots, statistical tables and any literature references extracted from the summary.

**Reason:** This tool will automatically embed images, build statistics cards, and format the report according to the prescribed layout.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

