# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requested a concise HTML report summarizing key metrics from the analysis of the q96c45_ATP system. The primary data source is the analysis_summary.jsonl file, which contains all computed statistics and paths to plots. Generating the report directly from this file meets the deliverable requirements and adheres to the tool usage guidelines. Literature context is optional; for brevity and because the summary already contains detailed metrics, we will not perform an additional literature search in this workflow.

## Overview

1. Read and parse the analysis_summary.jsonl file to obtain analysis data and image paths. 2. Generate a comprehensive HTML report with embedded images, key statistics, and organized sections. 3. Place the report at /home/akp66103/workspace/agenticAI/campaigns/robustness/campaigns/pseudokin_37x2/run_01/q96c45_ATP/reporter/report.html.

## Report Focus

- Ligand pocket distance distribution
- Consensus RMSF of the protein
- Consensus DCCM (N‑lobe ↔ C‑lobe correlations)
- Dihedral PCA landscape entropy
- Ten key scalar descriptors and their average values across replicates

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to extract all analysis results, statistics, and associated image paths.

**Reason:** Need to load the computed metrics and visualizations for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional HTML report embedding all relevant plots and key statistics. The report will be comprehensive, following the requested layout and style guidelines.

**Reason:** Produce the final deliverable in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

