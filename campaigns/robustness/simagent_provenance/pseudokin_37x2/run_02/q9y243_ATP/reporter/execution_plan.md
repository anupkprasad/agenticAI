# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a concise HTML report that embeds all visualisations from the analysis_summary.jsonl file and provides context from relevant literature. The workflow therefore needs to (1) load the analysis data, (2) build targeted PubMed queries based on the analysis types, (3) fetch the most recent papers for each query, and (4) generate a single‑simulation HTML report that includes the figures, key statistics, and literature references.

## Overview

1️⃣ Load the `analysis_summary.jsonl` file. 2️⃣ Create PubMed search queries that focus on the specific descriptors calculated. 3️⃣ Retrieve a handful of recent abstracts for each query. 4️⃣ Feed the parsed analysis data and the literature references into `generate_html_report`, producing `report.html` in the reporter directory.

## Report Focus

- ATP ligand positioning and orientation dynamics
- Pocket residue flexibility (χ1, RMSF)
- Inter‑lobe communication (DCCM)
- Entropy of dihedral‑PCA space

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing all per‑replica metrics, mean‑SD tables, and image paths.

**Reason:** All subsequent steps rely on the parsed analysis results.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Search Queries

**Tool:** `generate_literature_queries`

**Description:** Create a list of search strings that target the protein–ATP holo context, the descriptors computed, and recent literature.

**Reason:** To tailor PubMed searches to the specific analysis performed.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "pocket \u03c71",
    "C\u03b1 RMSF",
    "DCCM",
    "dihedral\u2011PCA entropy"
  ],
  "user_goal": "Analyze the 200\u2011ns trajectories for each protein\u2013ATP holo system and interpret the 10\u2011descriptor feature matrix.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Query PubMed with the generated strings, retrieving up to 5 recent abstracts for each.

**Reason:** Gather literature that can be cited in the report.

**Parameters:**
```json
{
  "query": "{{queries}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds all images, displays key statistics, and lists the literature references.

**Reason:** This is the final deliverable that satisfies the user’s request.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_summary}}",
  "literature_refs": "{{pubmed_results}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

