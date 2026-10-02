# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already executed all per‑system MD analyses and produced a single `analysis_summary.jsonl` file that contains the computed metrics and the file paths to all relevant plots.  Our job is to parse that summary, extract the key numerical descriptors, and embed the associated images in a professional, modern HTML report.  Because the workflow is strictly per‑simulation, we use the `generate_html_report` tool (no combined report).  We do not need to re‑run any simulations, so the plan consists of two deterministic steps: reading the summary and generating the report.  Optionally, we can generate literature queries to enrich the report, but this is not strictly required.

## Overview

1️⃣ Read the `analysis_summary.jsonl` file to obtain the analysis results and image paths. 2️⃣ Feed those results into `generate_html_report` to produce a `report.html` that contains embedded plots, statistical cards, and a concise narrative.

## Report Focus

- ATP COM distance (mean ± std)
- Pocket χ1 orientation (circular mean ± std)
- Consensus‑mapped Cα RMSF
- N‑lobe ↔ C‑lobe DCCM mean
- Shared‑reference dihedral PCA scalar

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to load all per‑system metrics and image paths.

**Reason:** We need the raw data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all plots and displays key statistics in a modern layout.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive",
  "literature_refs": [],
  "pdb_data": null,
  "enriched_prompt": null
}
```

