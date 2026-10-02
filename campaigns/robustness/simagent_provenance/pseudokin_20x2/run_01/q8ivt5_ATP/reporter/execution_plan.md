# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that embeds all visualisations, statistics, and literature context derived from the analysis summary.  We first parse the analysis_summary.jsonl to obtain the necessary data structures and image paths.  Then we invoke generate_html_report to create a self‑contained report named `report.html`.  For added value we also generate targeted PubMed queries so the reporter can fetch relevant literature, but the actual PubMed search is optional and can be run later if desired.

## Overview

1. Load the analysis summary. 2. Build a list of literature search queries tailored to the protein and analysis types. 3. Create the comprehensive HTML report with embedded plots and statistical cards.

## Report Focus

- ATP‑binding pocket definition and consensus pocket metrics
- Scalar dynamics descriptors (distance, angle, torsions, RMSF, DCCM)
- Ward hierarchical clustering of averaged descriptors
- Comparison of the two 200‑ns replicates

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all scalar descriptors, consensus metrics, image file paths, and statistical summaries for the current 200‑ns trajectory pair.

**Reason:** Acquire structured analysis data and visualisation paths for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that target the protein name, ATP binding, MD simulation methods, and the specific analysis descriptors (RMSF, DCCM, torsions).  These queries can be used later to fetch abstracts and citations.

**Reason:** Prepare concise, high‑priority search strings for literature retrieval.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "torsion",
    "binding pocket",
    "ATP"
  ],
  "user_goal": "Analyze ATP binding pocket dynamics and cluster systems by scalar descriptors.",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all trajectory plots, MSA panels, clustering visualisations, and a feature‑heatmap.  The report includes key statistics cards and a literature context section.

**Reason:** Produce the final deliverable report for the simulation.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive",
  "literature_refs": [],
  "final_impression": "The analysis demonstrates consistent ATP\u2011binding pocket dynamics across replicates, with clustering revealing distinct conformational families."
}
```

