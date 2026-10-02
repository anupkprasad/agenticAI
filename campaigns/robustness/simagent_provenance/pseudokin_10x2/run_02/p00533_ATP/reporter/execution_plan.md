# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that incorporates the analysis results, key statistics, and literature context.  The workflow is straightforward: load the analysis summary, generate relevant PubMed queries, fetch a handful of citations, and finally generate a comprehensive HTML report that embeds all plots and statistics.

## Overview

1) Read analysis results from `analysis_summary.jsonl`. 2) Build PubMed search queries from the analysis types and the user goal. 3) Retrieve up to 5 recent citations for each query. 4) Generate a full HTML report (`report.html`) that embeds all images, displays key statistics cards, and includes the literature references.

## Report Focus

- Consensus RMSF and pocket flexibility
- Ligand pocket distance & orientation
- Cross‑lobe DCCM and dihedral PCA
- Literature context on pseudokinase dynamics

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains the per‑replicate analysis metrics and image file paths.

**Reason:** Need the analysis data and plot locations to build the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed query strings that combine the protein context with each analysis type.

**Reason:** Generate high‑priority search queries that are tailored to the protein and the specific analyses performed.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "distance",
    "orientation",
    "torsion"
  ],
  "user_goal": "Analyze the existing 200\u202fns production trajectories for the ten protein\u2011ATP holo complexes in the working directory, computing ligand pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF.",
  "protein_name": "Pseudokinase"
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Query PubMed for each generated query string and collect up to 5 recent citations.

**Reason:** Retrieve literature that contextualizes the observed dynamics in pseudokinases.

**Parameters:**
```json
{
  "query": "{{queries.priority1}} AND \"pseudokinase\" AND (\"MD simulation\" OR \"Molecular dynamics\")",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, fully‑self‑contained report that embeds all analysis plots and highlights key statistics.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_data}}",
  "literature_refs": "{{literature_refs}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

