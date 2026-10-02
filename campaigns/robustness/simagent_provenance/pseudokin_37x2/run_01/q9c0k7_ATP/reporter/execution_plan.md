# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis summary JSONL file contains all the scalar descriptors, statistical summaries, and image paths for the 37 MD trajectories. To produce a self‑contained HTML report for each simulation, we only need to (1) read that file and (2) feed the parsed data to the report‑generation tool. The report tool automatically embeds images, creates statistical cards, and lays out the content in a clean, professional format. No additional manual file handling or path specification is required. Literature context can be added optionally, but is not mandatory for the core report.

## Overview

1. Parse analysis_summary.jsonl → Python dict. 2. Pass dict to generate_html_report with output_file='report.html'. 3. The report is written to the dedicated reporter directory for the simulation.

## Report Focus

- Visualization of ATP COM distance, orientation, pocket χ1, RMSF, DCCM, PCA scalar
- Statistical comparison across the 37 trajectories
- Clustering dendrogram and heatmap
- Literature context on ATP‑binding and pseudokinase dynamics

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file that contains all computed descriptors and image file paths.

**Reason:** Load all analysis results and image references into a single data structure.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds the analysis images, displays key statistics, and provides a modern layout.

**Reason:** Produce the final deliverable; the tool automatically fills in the placeholders from the parsed data.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

