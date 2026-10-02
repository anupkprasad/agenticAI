# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The goal is to produce a concise, evidence‑based HTML report for a single molecular system using already generated analysis data.  The only required operations are to read the analysis summary (which contains all numeric results and image file paths) and to feed that data into the report generator.  Optional literature context can be added by performing a PubMed search, but this is not mandatory for a valid report.

## Overview

1️⃣ Read the per‑system `analysis_summary.jsonl`.  2️⃣ Feed the parsed data into `generate_html_report` to create a fully‑formatted, self‑contained HTML document named `report.html`.  3️⃣ (Optional) Search PubMed for a few context‑relevant papers and embed the references in the report.

## Report Focus

- ATP binding pocket dynamics (COM distance/orientation)
- Pocket torsional variability (χ1 mean/SD)
- Cα RMSF mapping to consensus pocket
- Lobe‑level correlation (N‑ vs. C‑lobe DCCM)
- Shared‑reference dihedral‑PCA entropy

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain all metrics, statistics, and image paths for the current system.

**Reason:** Load all analysis results that will drive the visual and textual content of the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds all images, displays key statistics, and follows a modern, professional layout.

**Reason:** Produce the final deliverable that can be viewed directly in a browser.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

