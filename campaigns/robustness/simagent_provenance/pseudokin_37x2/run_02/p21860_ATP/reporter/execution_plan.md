# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis results have already been computed and stored in the `analysis_summary.jsonl` file. To produce the requested scientific report we need to (1) parse this summary, (2) optionally add literature context by querying PubMed, and (3) generate a comprehensive HTML report that embeds the visualisations, displays key statistics, and includes the retrieved literature references. This minimal yet complete workflow satisfies all user requirements while keeping complexity low.

## Overview

The plan reads the analysis summary, performs a PubMed search for relevant literature on pseudokinase ATP‑binding dynamics, and creates a professional HTML report with embedded plots and statistical summaries.

## Report Focus

- ATP COM distance to consensus pocket
- ATP orientation relative to pocket axis
- Side‑chain χ1 circular statistics
- Cα RMSF over consensus‑mapped residues
- N‑/C‑lobe DCCM correlation
- Shared‑reference dihedral PCA entropy

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to retrieve per‑system metrics, statistics, and image paths.

**Reason:** Load the computed data needed for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Contextual Literature

**Tool:** `search_pubmed`

**Description:** Query PubMed for recent studies on pseudokinase ATP dynamics and MD simulations to provide literature context.

**Reason:** Retrieve a concise set of relevant articles for inclusion in the report.

**Parameters:**
```json
{
  "query": "pseudokinase ATP MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds the analysis visualisations, displays key statistics, and lists the retrieved literature references.

**Reason:** Produce the final deliverable with all required content.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

