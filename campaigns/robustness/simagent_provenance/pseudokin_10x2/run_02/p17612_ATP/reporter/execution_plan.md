# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already run the trajectory analyses and produced a single JSONL file (`analysis_summary.jsonl`) containing all per‑system metrics, statistics and image paths.  Our role is to parse this file, extract the key descriptors, and embed the associated visualizations into a polished, self‑contained HTML report.  Because the user only requested a per‑simulation report (not a combined multi‑simulation comparison), we use the single‑simulation `generate_html_report` tool.  No further preprocessing or additional simulations are performed.

## Overview

1. Read and parse the `analysis_summary.jsonl` file. 2. Feed the parsed data to the report generator, which will automatically locate all referenced image files, embed them as base‑64, and populate statistical cards. 3. Produce `report.html` inside the reporter working directory.  The report will feature a modern layout, dedicated sections for each descriptor type, and a concise summary of the clustering and key findings.

## Report Focus

- ATP‑binding pocket dynamics (COM distance, axis angle, χ1 torsion)
- Structural stability (Cα RMSF, DCCM, dihedral PCA)
- Clustering insights (Ward hierarchy, dendrogram, feature heat‑map)

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all scalar descriptors, statistical summaries, and paths to visualization images.

**Reason:** We need the raw analysis data to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report with embedded plots, statistical cards, and a brief interpretation of the key clustering results.

**Reason:** This produces the final deliverable requested by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

