# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a concise, data‑driven HTML report that summarises the per‑system MD analysis stored in `analysis_summary.jsonl`. The workflow is deterministic: first load the summary, then generate the report using the built‑in HTML generator. We do not need any literature searches in this single‑simulation report, but we will include a few targeted PubMed queries for future enrichment. The plan therefore focuses on reading the summary and producing the report, while keeping the steps clear and reproducible.

## Overview

1. Load `analysis_summary.jsonl` containing all scalar descriptors, statistics, and image file paths. 2. Pass the parsed data to `generate_html_report` to create a single `report.html` file in the reporter directory. 3. Optionally generate a set of PubMed queries for literature context. 4. Produce the final JSON plan with the required tool calls.

## Report Focus

- ATP pocket occupancy and COM distance dynamics
- Pocket side‑chain χ₁ rotamer distribution
- Consensus RMSF of the protein scaffold
- N‑lobe ↔ C‑lobe inter‑domain correlation
- Dihedral PCA dynamics scalar
- Overall hierarchical clustering of systems

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to extract all analysis results, statistics, and image paths.

**Reason:** Load all per‑system descriptors and plot paths for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report embedding the images and key statistics extracted from the summary.

**Reason:** Produce the final deliverable that can be viewed in a web browser.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

