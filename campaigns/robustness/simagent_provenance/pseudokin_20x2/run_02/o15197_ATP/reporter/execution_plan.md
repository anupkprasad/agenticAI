# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report requires the consolidated analysis data and contextual literature. We first read the analysis summary JSONL to obtain all per‑system metrics and image paths. Next, we query PubMed with a combined, topic‑focused search to pull recent, relevant studies on pseudokinase ATP dynamics and the specific analytical methods used. Finally, we feed the analysis data and the retrieved literature into the HTML report generator, which will embed the plots and summary cards automatically. This two‑step workflow keeps the report comprehensive while leveraging only the provided tools.

## Overview

1. Load analysis results from `analysis/analysis_summary.jsonl`. 2. Search PubMed for recent literature on pseudokinase ATP simulations and the key analytical techniques (consensus DCCM, dihedral PCA, etc.). 3. Generate a single, fully‑embedded HTML report (`report.html`) in the reporter directory that includes plots, statistics, and literature context.

## Report Focus

- Per‑system dynamics descriptors (e.g., ATP COM distance, pocket χ₁, DCCM)
- Consensus metrics across replicates
- Literature context for pseudokinase ATP binding and analytical methods

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain all analysis metrics, statistics, and image file paths.

**Reason:** Need to load the analysis results for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for Contextual Literature

**Tool:** `search_pubmed`

**Description:** Retrieve recent papers on pseudokinase ATP dynamics and the analytical methods applied.

**Reason:** Provide up‑to‑date literature references to contextualize the findings.

**Parameters:**
```json
{
  "query": "pseudokinase ATP MD simulation OR ATP binding pocket dynamics OR consensus DCCM protein kinases OR dihedral PCA protein kinase flexibility",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report with embedded images, key statistics, and literature citations.

**Reason:** Produce the final deliverable for the current simulation run.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

