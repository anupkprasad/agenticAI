# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis data are already stored in `analysis/analysis_summary.jsonl`.  Reading this file gives us all computed descriptors, the per‑system statistics and the file paths to the visualisations that the report must embed.  The only further requirement is to create a single, fully self‑contained HTML report in the reporter directory.  Because literature context is optional, we simply supply a list of PubMed search queries that the user can run independently if desired.  No additional preprocessing or simulation work is needed.

## Overview

1. Load the analysis summary. 2. Feed the parsed data to the report generator to produce `report.html` in the reporter directory. 3. Provide a set of suggested literature search queries.

## Report Focus

- Hierarchical clustering of the 37 holo systems
- Key dynamic descriptors (ATP COM distance, orientation, pocket χ₁, RMSF, DCCM, dihedral PCA entropy)
- Interpretation with a k = 4 cut
- Contextual literature on ATP binding in pseudokinases

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all per‑system descriptors, statistics and image paths.

**Reason:** Need to obtain the analysis data for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds all visualisations and displays the key statistics.

**Reason:** Produce the final deliverable in the required location.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

