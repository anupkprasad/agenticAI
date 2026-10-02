# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a comprehensive single‑simulation HTML report that includes embedded plots, key statistics, and literature context. The workflow therefore needs to (1) parse the analysis_summary.jsonl to obtain all analysis results and image paths, (2) generate relevant literature search queries based on the performed analyses and the protein system, (3) fetch the most recent, pertinent literature via PubMed, and (4) build the HTML report embedding the plots and summarizing the findings. All intermediate data are handled automatically by the available tools, and the final report is written to `report.html` in the reporter directory.

## Overview

1️⃣ Read analysis results → 2️⃣ Auto‑generate literature queries → 3️⃣ Pull PubMed references → 4️⃣ Produce a styled HTML report with plots, statistics, and literature citations.

## Report Focus

- Ligand‑pocket interaction dynamics
- Consensus protein flexibility (RMSF & DCCM)
- Dihedral PCA entropy
- Clustering and feature interpretation

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing all per‑trajectory metrics, statistics, and figure file paths.

**Reason:** Need the raw analysis data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Extract Metadata for Literature Search

**Tool:** ``

**Description:** From the parsed data, pull the list of analysis types, the protein name (if available), and any relevant summary statistics.

**Reason:** These inputs are required for generating focused PubMed queries.

**Parameters:**
```json
{}
```

### Step 3: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a prioritized set of PubMed search strings that target the protein, the specific MD analysis methods, and the user’s hypothesis.

**Reason:** To obtain specific, up‑to‑date literature that contextualizes the findings.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "pocket \u03c71",
    "C\u03b1 RMSF",
    "DCCM",
    "dihedral PCA"
  ],
  "user_goal": "Analyze the existing 37 protein\u2013ATP holo trajectories: compute ligand\u2011pocket distance, consensus DCCM, consensus RMSF, consensus torsions, DCCM, dihedral PCA, nearby contacts, and protein RMSF; then extract the ten scalar descriptors\u2026",
  "protein_name": "pseudokinase",
  "analysis_stats": {
    "RMSF mean": 0.25,
    "DCCM mean": 0.1
  }
}
```

### Step 4: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the top priority PubMed queries and gather article metadata (title, authors, abstract, PMID).

**Reason:** Retrieve recent, high‑impact papers relevant to the analysis.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding site dynamics simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report embedding all analysis figures, presenting key statistics in cards, and listing the literature references.

**Reason:** Produce the final user‑deliverable in the required format.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

