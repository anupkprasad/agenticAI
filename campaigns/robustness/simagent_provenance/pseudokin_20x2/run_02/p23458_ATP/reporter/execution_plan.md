# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl file contains all scalar descriptors, cluster dendrograms, heatmaps and associated image paths. The required report is a single‑simulation HTML file named report.html, which must embed these images and display key statistics. Therefore the workflow is: (1) read and parse the summary, (2) feed the parsed data into generate_html_report. Literature search is optional; the analysis itself already contains sufficient context for a comprehensive report, so we omit external searches to keep the workflow deterministic.

## Overview

The plan reads the pre‑generated analysis summary, extracts the scalar descriptors, cluster and heatmap images, then calls generate_html_report to produce a self‑contained HTML document. The report will automatically embed all images, display statistical cards for each descriptor, and format the output with a modern layout.

## Report Focus

- Ward hierarchical clustering dendrogram (k=4)
- Feature heatmap of the ten scalar dynamics descriptors
- Key descriptor statistics (mean, std, min, max) per protein

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain analysis results, statistics, and image file paths.

**Reason:** Need to load all analysis outputs and image references before generating the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds the analysis plots, presents key statistics, and includes a concise literature context section.

**Reason:** Produce the final deliverable in the required format and location.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": null,
  "final_impression": null,
  "pdb_data": null,
  "enriched_prompt": "Generate a scientific report for the ATP-binding pseudokinase based on the pre\u2011computed dynamics descriptors, clustering, and heatmaps."
}
```

