# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that incorporates all analysis results, visualisations and key statistics from the provided analysis_summary.jsonl file.  The workflow is straightforward: load the JSONL data, feed it to the report generator, and output a self‑contained report.  Literature search is optional; in this plan it is omitted to keep the process deterministic and avoid the need for dynamic query handling.

## Overview

1. Parse the analysis_summary.jsonl file to obtain all scalar descriptors, images and metadata. 2. Pass the parsed data directly to generate_html_report, requesting a comprehensive HTML report named report.html.  The report will embed all visualisations, display statistical cards, and organise sections per analysis type.

## Report Focus

- ATP binding‑site dynamics and ligand COM distances
- Pocket flexibility (χ1 torsion statistics)
- Lobe‑to‑lobe inter‑domain correlations
- Consensus RMSF and DCCM patterns
- Entropy of shared‑reference dihedral PCA

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file located in the analysis sub‑directory.

**Reason:** Need the complete set of analysis results and image paths for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, comprehensive HTML report that embeds all visualisations and displays key statistics.

**Reason:** Produce the final deliverable that meets the user’s specifications.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

