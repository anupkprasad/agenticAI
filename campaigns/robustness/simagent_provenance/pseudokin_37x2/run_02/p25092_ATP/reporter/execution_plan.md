# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has provided a pre‑computed analysis summary (JSONL) for a single MD simulation of a holo‑ATP pseudokinase. The goal is to convert this raw data into a polished HTML report that includes embedded visualizations, key statistics, and a concise narrative. No additional HPC steps are required. The workflow therefore consists of two core operations: parsing the analysis summary and generating the report. Literature context is optional; in this plan we focus on the data‑driven report and leave literature search for a future extension.

## Overview

1. Load the per‑trajectory analysis results from `analysis/analysis_summary.jsonl`. 2. Pass the parsed data to the report generator to create a comprehensive, self‑contained HTML file (`report.html`) in the reporter directory. 3. The report will embed all analysis plots, display statistical cards, and present a concise interpretation of the key descriptors (e.g., ATP–pocket distance, side‑chain χ₁, RMSF, DCCM, PCA scalar).

## Report Focus

- ATP binding pocket dynamics (COM–pocket distance & orientation)
- Conformational coupling between N‑ and C‑lobes (DCCM correlations)
- Side‑chain χ₁ distributions and overall flexibility (RMSF, torsions)

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing all computed descriptors, statistics, and image file paths.

**Reason:** Load the analysis data that will feed the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report embedding all plots and key statistics.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

