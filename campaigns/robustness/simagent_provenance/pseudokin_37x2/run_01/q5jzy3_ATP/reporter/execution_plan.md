# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has provided a complete set of per‑simulation analysis results in the file `analysis/analysis_summary.jsonl`.  The only remaining tasks are to parse that file, extract the key statistics and image paths, and create a single, comprehensive HTML report in the reporter directory.  Because the analysis data already contains all necessary plots and metrics, a literature search is optional; the report will be generated using the available data and the built‑in literature context that the report generator will automatically provide if requested.  This workflow is simple, deterministic, and fully compatible with the existing toolset.

## Overview

1. Read the analysis summary. 2. Feed the parsed data into `generate_html_report` to produce a professional, self‑contained HTML report (`report.html`).  The report will embed all images, display key statistics, and summarize the findings for each of the 37 protein‑ATP holo systems.

## Report Focus

- Ligand‑pocket COM distances and orientations
- Pocket side‑chain χ1 circular statistics
- Consensus‑mapped Cα RMSF (mean & std)
- N‑lobe ↔ C‑lobe DCCM correlation
- Shared‑reference dihedral PCA dynamics
- Hierarchical clustering of scalar descriptors
- Literature context linking findings to known protein‑ATP mechanisms

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to retrieve all per‑system metrics, statistics, and image file paths.

**Reason:** Load the complete analysis dataset that will feed the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds all plots, displays key statistics, and includes a brief literature context section.

**Reason:** Produce the final deliverable that satisfies the user’s reporting requirement.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

