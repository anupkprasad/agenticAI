# Reporter Execution Plan

**Generated:** 1791301958.4401546

## LLM Reasoning

The user wants a comprehensive HTML report that integrates the analysis results from a single MD trajectory with literature context on activation‑loop dynamics and allosteric regulation. The plan will read the pre‑generated `analysis_summary.jsonl`, perform a targeted PubMed search for relevant literature, and finally generate a self‑contained HTML report that embeds all plots, statistical cards, and literature references.

## Overview

1. Parse the analysis summary. 2. Query PubMed for key literature on pseudokinase activation‑loop dynamics and ATP‑binding allostery. 3. Collate the retrieved references. 4. Produce a professional HTML report that overlays the analysis data with the literature context.

## Report Focus

- Activation‑loop dynamics and flexibility
- Allosteric regulation through ATP binding

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to obtain all statistics, metrics and image paths for the simulation.

**Reason:** Need the raw analysis data for report generation.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: PubMed Search – Activation Loop Dynamics

**Tool:** `search_pubmed`

**Description:** Retrieve recent papers that discuss activation‑loop dynamics in pseudokinases using MD simulation or structural analysis.

**Reason:** Provide context on the dynamical behavior of the activation loop.

**Parameters:**
```json
{
  "query": "pseudokinase activation loop dynamics MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: PubMed Search – ATP Binding Allostery

**Tool:** `search_pubmed`

**Description:** Gather literature describing ATP‑binding and allosteric regulation in pseudokinases or related kinases.

**Reason:** Support interpretation of COM distance, DCCM, and RMSF results.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding allosteric regulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds all analysis visualisations and summarises the literature findings.

**Reason:** Deliver the final product to the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

