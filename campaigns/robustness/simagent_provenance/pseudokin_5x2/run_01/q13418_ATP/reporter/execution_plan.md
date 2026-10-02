# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report generation workflow requires two main steps: first to read and parse the JSONL summary file that contains all scalar descriptors, statistics, and file paths to images produced by the analysis agent; second to feed that parsed data into the report generator which will embed the visualisations, display key statistics, and optionally add literature context.  No additional tools are needed beyond the two specified for reading the summary and producing the HTML.  Literature queries are optional and will be generated using the provided query‑generation helper based on the analysis types present in the summary.

## Overview

1️⃣ Read the analysis summary from `analysis/analysis_summary.jsonl`. 2️⃣ Generate a comprehensive HTML report (`report.html`) that automatically embeds the images, displays the statistical descriptors in a clean layout, and incorporates a brief literature review. 3️⃣ Optionally create PubMed queries to fetch recent literature for contextualisation.

## Report Focus

- Consensus pocket–ligand distance distribution
- ATP–pocket axis alignment
- Pocket side‑chain χ1 variability
- Consensus‑mapped Cα RMSF patterns
- Inter‑lobe DCCM correlation
- Shared‑reference dihedral PCA entropy

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the `analysis_summary.jsonl` file, extracting all recorded metrics, statistics, and image paths.

**Reason:** We need the analysis data in structured form before we can generate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, comprehensive HTML report that embeds all visualisations, displays key statistical cards, and includes literature context.

**Reason:** This tool will produce the final deliverable report with embedded images and formatted sections.

**Parameters:**
```json
{
  "analysis_data": "$(read_analysis_summary.output)",
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

