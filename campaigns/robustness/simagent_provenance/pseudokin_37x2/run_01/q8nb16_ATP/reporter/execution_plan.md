# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a concise, data‑rich HTML report that includes the key analysis metrics from the existing trajectory files and contextual literature references. We will (1) parse the pre‑generated analysis_summary.jsonl file, (2) auto‑generate PubMed queries based on the analyses performed, (3) fetch recent literature, and (4) feed all this into `generate_html_report` to produce the final `report.html` in the reporter directory.

## Overview

A three‑stage workflow: read analysis data → search literature → generate the HTML report.

## Report Focus

- Ligand‑Pocket Distance & Orientation
- Consensus RMSF and DCCM
- Dihedral PCA Entropy Landscape

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the JSONL file containing all per‑analysis metrics and image paths.

**Reason:** Need the analysis data and file paths for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a set of PubMed queries tailored to the protein and the analyses performed.

**Reason:** To generate targeted literature queries that will enrich the report.

**Parameters:**
```json
{
  "analysis_types": [
    "ligand-pocket distance",
    "consensus DCCM",
    "consensus RMSF",
    "dihedral PCA",
    "protein RMSF",
    "nearby contacts"
  ],
  "user_goal": "Analyze the existing 200\u2011ns trajectories for q8nb16_ATP, computing ligand\u2011pocket distance, consensus DCCM, consensus RMSF, consensus torsions, global DCCM, dihedral PCA, nearby contacts, and protein RMSF. Extract descriptors such as ATP COM\u2011to\u2011pocket distance, ATP orientation relative to pocket axis, consensus C\u03b1 RMSF, pocket side\u2011chain \u03c7\u2081, N\u2011lobe \u2194 C\u2011lobe DCCM, and dihedral PCA entropy.",
  "protein_name": "q8nb16",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed (Top Query)

**Tool:** `search_pubmed`

**Description:** Query PubMed using the highest‑priority literature query to retrieve recent, relevant articles.

**Reason:** Provide up‑to‑date literature context for the analysis.

**Parameters:**
```json
{
  "query": "{{GENERATED_QUERY_FROM_STEP_2.priority1}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create the final HTML report embedding analysis images, key statistics, and literature citations.

**Reason:** Produce the deliverable report for the user.

**Parameters:**
```json
{
  "analysis_data": "{{STEP_1.analysis_data}}",
  "literature_refs": "{{STEP_3.pubmed_results}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

