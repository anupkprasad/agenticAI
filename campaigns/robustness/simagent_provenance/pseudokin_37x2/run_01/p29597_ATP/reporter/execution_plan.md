# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already run the full MD analysis pipeline and stored all results, statistics and image paths in `analysis/analysis_summary.jsonl`.  Our job is to parse that file, extract the key quantitative descriptors, and generate a concise yet comprehensive HTML report that embeds all visualizations and highlights the most important metrics.  The report should include the ten scalar descriptors requested, a feature‑heatmap with Ward clustering, and a short literature context.  We will use the provided tools: `read_analysis_summary` to load the data and `generate_html_report` to create the final document.  No additional analysis or simulation steps are required.

## Overview

1️⃣ Read and parse the analysis summary JSONL. 2️⃣ Pass the parsed data to the report generator, requesting a comprehensive HTML file named `report.html`. 3️⃣ The generator will embed images, display key statistics cards, and append a literature section (if provided). 4️⃣ The resulting file will reside in the reporter’s working directory (`.../reporter/`).

## Report Focus

- ATP COM distance (mean & std)
- ATP axis angle (mean & std)
- Pocket χ1 circular mean & std
- Consensus‑Cα RMSF mean & std
- N‑lobe↔C‑lobe DCCM mean
- Dihedral‑PCA landscape entropy
- Feature‑heatmap with Ward dendrogram
- Key visualizations (RMSD, RMSF, DCCM, dihedral‑PCA, contacts)
- Literature context (MD studies on ATP binding & pseudokinase flexibility)
- Final scientific impressions

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the `analysis_summary.jsonl` file to obtain all computed metrics, statistics, and image file paths.

**Reason:** We need the full set of analysis results to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report (`report.html`) that embeds all visualizations, displays key statistics cards for the ten scalar descriptors, and includes a literature context section.

**Reason:** This is the final deliverable that the user requested.

**Parameters:**
```json
{
  "analysis_data": "REPLACE_WITH_RESULT_FROM_READ_ANALYSIS_SUMMARY",
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

