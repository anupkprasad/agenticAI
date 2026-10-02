# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user’s objective is to generate a single, comprehensive HTML report for one molecular dynamics simulation.  The report must include all visualisations and statistics that have already been produced by the analysis agent (available in `analysis/analysis_summary.jsonl`).  No new analyses or simulations are to be performed.  The most efficient path is: (1) read the summary file to extract all the analysis data and the paths to the embedded images; (2) (optionally) run a PubMed search to provide contextual literature; and (3) feed the extracted data and literature references into `generate_html_report` to produce a polished, self‑contained `report.html`.  This workflow respects the tool constraints and the path conventions specified by the user.

## Overview

1️⃣ Read `analysis/analysis_summary.jsonl` with `read_analysis_summary`. 2️⃣ (Optional) Query PubMed for recent literature on ATP‑binding pseudokinases and the specific descriptors used. 3️⃣ Create the final report with `generate_html_report`, embedding all images and key statistics, and include a brief literature context section.

## Report Focus

- Consensus ATP‑binding pocket metrics (COM distance/angle, χ₁ mean/SD)
- Mapped‑residue dynamics (Cα RMSF, DCCM mean, PCA scalar)
- Overall clustering of descriptors across the 20 proteins

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis summary JSONL file to obtain all computed descriptors, statistical summaries, and image file paths for the current simulation.

**Reason:** Load all pre‑computed analysis results that will be embedded in the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Contextual Literature

**Tool:** `search_pubmed`

**Description:** Execute a PubMed search for recent papers on pseudokinase ATP‑binding dynamics, focusing on descriptors such as RMSF, COM distances, torsional analyses, and PCA.  The query list is derived from the analysis types performed.

**Reason:** Provide up‑to‑date literature references that can be cited in the report to contextualise the findings.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding dynamics RMSF \"2022/2024\"",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 3
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, self‑contained HTML report that embeds all analysis plots (as base64), displays key statistics in cards, and includes the literature context gathered above.

**Reason:** Produce the final deliverable as specified.

**Parameters:**
```json
{
  "analysis_data": "<parsed data from read_analysis_summary output>",
  "literature_refs": "<list of PubMed citations from search_pubmed output>",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

