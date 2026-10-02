# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The workflow is straightforward: the analysis results for this single MD simulation are already collated in `analysis/analysis_summary.jsonl`. We first read and parse that file to obtain all scalar metrics and paths to the generated plots. These data, together with a concise literature context, are then fed into `generate_html_report` to produce a self‑contained HTML summary (saved as `report.html` in the reporter directory). No additional analyses or simulation steps are required.

## Overview

1. Load the pre‑computed analysis summary. 2. Optionally enrich the report with a short literature review (searching PubMed for recent MD/kinase studies). 3. Generate the HTML report with embedded figures and key statistics.

## Report Focus

- Consensus pocket metrics (distance, orientation, χ₁ distribution)
- Dynamic coupling (N‑ vs C‑lobe DCCM)
- Flexibility (Cα RMSF) and dihedral PCA entropy

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all per‑system metrics and image file paths.

**Reason:** We need the analysis data and figure locations for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search Literature (Optional)

**Tool:** `search_pubmed`

**Description:** Retrieve a small set of recent papers that provide context for kinase MD studies and the specific descriptors used.

**Reason:** Adding literature citations gives scientific weight to the findings and is required by the report specification.

**Parameters:**
```json
{
  "query": "kinase MD simulation RMSF 2021..2024",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 3
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all analysis plots, displays key statistics, and includes the literature references.

**Reason:** This produces the final deliverable as specified.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "enriched_prompt": "Generate a concise HTML report summarizing the ATP\u2011holo MD analysis of 37 pseudokinase structures, highlighting consensus pocket metrics, side\u2011chain dynamics, RMSF, DCCM, and dihedral PCA entropy."
}
```

