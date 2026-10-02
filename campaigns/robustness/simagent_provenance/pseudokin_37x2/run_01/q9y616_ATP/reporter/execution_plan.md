# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

We must read the already‑generated analysis summary, optionally enrich the report with literature context, and then create a polished HTML report that embeds all plots and key statistics.

## Overview

1) Parse the `analysis_summary.jsonl` file. 2) Build PubMed queries that match the protein, analysis methods, and the user goal. 3) Retrieve a small set of relevant references. 4) Generate a comprehensive HTML report that includes the plots, statistics, and literature citations.

## Report Focus

- Ligand‑pocket interaction metrics (distance & angle)
- Consensus structural descriptors (RMSF, DCCM, PCA entropy)
- Cluster‑based classification of the 37 holo structures
- Literature context on pseudokinase dynamics and MD analysis

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain all analysis results and image paths.

**Reason:** All downstream steps depend on the analysis data.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Search Queries

**Tool:** `generate_literature_queries`

**Description:** Create a prioritized list of PubMed queries based on the protein, analysis methods, and user goal.

**Reason:** We need context‑aware literature queries.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DCCM",
    "PCA",
    "Consensus",
    "Pocket",
    "Torsion"
  ],
  "user_goal": "Perform the ligand\u2011pocket distance, consensus_DCCM, consensus_RMSF, consensus_torsions, DCCM, dihedral_PCA, nearby, and protein_RMSF analyses on the existing 200\u2011ns trajectories of the 37 protein\u2013ATP holo structures\u2026",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed for Relevant Articles

**Tool:** `search_pubmed`

**Description:** Execute each query to fetch up to 5 recent references per query.

**Reason:** Collect citations to enrich the report.

**Parameters:**
```json
{
  "query": "{{GENERATED_QUERY}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": null
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all plots, key statistics, and literature references.

**Reason:** This is the final deliverable.

**Parameters:**
```json
{
  "analysis_data": "{{READ_SUMMARY_OUTPUT}}",
  "literature_refs": "{{PUBMED_REFERENCES}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

