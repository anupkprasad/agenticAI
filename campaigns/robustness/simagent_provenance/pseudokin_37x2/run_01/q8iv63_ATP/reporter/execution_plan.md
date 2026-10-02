# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has requested a concise, professional HTML report that summarizes the per‑system analysis stored in the “analysis_summary.jsonl” file. The workflow therefore needs to (1) load the analysis data, (2) optionally retrieve relevant literature for context, and (3) generate the report using the provided tooling. No additional data transformations or clustering are required at this step, as those were completed in previous stages.

## Overview

1. Read the analysis summary.
2. Generate literature queries based on the analysis types and the user’s hypothesis.
3. Search PubMed for the most relevant articles.
4. Produce a comprehensive HTML report that embeds all plots, presents key statistics, and includes literature references.

## Report Focus

- Summary of key quantitative metrics (mean, SD, min, max)
- Visual comparison of ligand pocket distance, RMSF, and DCCM across systems
- Contextual literature highlighting recent advances in pseudokinase MD studies

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all statistical metrics, image paths, and metadata.

**Reason:** Load the analysis results for subsequent processing.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a prioritized list of PubMed queries that target the protein, MD simulation context, and the specific analyses performed.

**Reason:** Produce focused search terms for literature retrieval.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DCCM",
    "torsions",
    "dihedral PCA"
  ],
  "user_goal": "Generate a scientific report summarizing per\u2011system MD analysis of protein\u2013ATP holo structures.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent (≤10 years) PubMed articles for each generated query.

**Reason:** Obtain context and recent findings to include in the report.

**Parameters:**
```json
{
  "query": "{{queries_for_pubmed}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds all images, presents key statistics, and lists literature references.

**Reason:** Deliver the final, self‑contained HTML report.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_data}}",
  "literature_refs": "{{pubmed_results}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

