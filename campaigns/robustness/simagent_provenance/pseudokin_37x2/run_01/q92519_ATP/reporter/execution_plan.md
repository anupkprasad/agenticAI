# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a comprehensive HTML report that includes all analysis plots and key statistics from the MD trajectory analyses. We will first read the analysis summary, optionally enrich the report with literature context, and finally generate the report with embedded images and statistics. The report will be named "report.html" and placed in the dedicated reporter directory.

## Overview

1. Parse the analysis summary JSONL file to collect all analysis results, statistics, and image paths. 2. Generate targeted PubMed search queries based on the analysis types and protein context. 3. Retrieve literature references for those queries. 4. Produce a professional HTML report that embeds the plots, displays key statistics, and cites relevant literature.

## Report Focus

- Key statistical descriptors (means, SDs, entropies)
- Visualizations of ligand pocket dynamics and inter‑lobe coupling
- Literature context for pseudokinase dynamics and MD analysis methods

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all per‑system metrics, statistics, and image file paths.

**Reason:** We need the raw data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries tailored to the protein (pseudokinase), the simulation methods, and the analysis techniques used.

**Reason:** These queries will drive the literature search for relevant context.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "Dihedral PCA",
    "Pocket Distance",
    "Ligand Binding",
    "ATP Orientation"
  ],
  "user_goal": "Provide context and validation for the MD-derived descriptors of the pseudokinase holo complexes.",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** For each query returned above, retrieve up to 5 recent articles (last 10 years) with full abstracts to use as literature references.

**Reason:** We need actual literature references to embed in the report.

**Parameters:**
```json
{
  "query": "pseudokinase MD simulation DCCM",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional HTML report titled 'report.html' that embeds all analysis plots, displays key statistics, and cites the retrieved literature.

**Reason:** This produces the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

