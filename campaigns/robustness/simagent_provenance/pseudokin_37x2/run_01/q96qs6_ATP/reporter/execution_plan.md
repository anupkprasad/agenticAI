# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To produce a single‑simulation HTML report for the q96qs6_ATP trajectory set, the workflow only needs to ingest the already‑generated analysis summary and feed it to the HTML generator. The summary contains all metric values, statistics and paths to the analysis plots, so no further data manipulation is required. Optionally, literature context can be added by generating PubMed queries, but this step is not mandatory for the report creation itself.

## Overview

The plan follows a minimal two‑step procedure: (1) read the analysis summary file; (2) generate a comprehensive HTML report that automatically embeds the analysis figures, displays key statistics, and can incorporate literature references if desired.

## Report Focus

- Key statistical descriptors of ATP–protein interaction (COM distance, orientation, pocket χ₁, RMSF, DCCM, dihedral‑PCA entropy)
- Visual presentation of ligand pocket dynamics, protein RMSF, and consensus analyses

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains the output of all eight analyses for the two replicas and their averages.

**Reason:** Load all analysis results, statistics, and image paths into a structured dictionary.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, self‑contained HTML document that embeds the analysis plots, displays key statistics cards, and optionally lists literature references.

**Reason:** Produce the final deliverable for the q96qs6_ATP system.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

