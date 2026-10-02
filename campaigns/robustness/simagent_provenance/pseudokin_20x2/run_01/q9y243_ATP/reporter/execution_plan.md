# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requires a comprehensive HTML report summarising the scalar dynamics descriptors from two 200‑ns replicates of the q9y243–ATP holo system, enriched with literature context. The workflow therefore involves: (1) parsing the already‑generated analysis summary, (2) formulating targeted PubMed queries using the supplied analysis types, (3) retrieving relevant literature, and (4) assembling all information into a self‑contained HTML report.

## Overview

1️⃣ Parse analysis_summary.jsonl → 2️⃣ Generate PubMed queries → 3️⃣ Fetch literature → 4️⃣ Produce report.html

## Report Focus

- Dynamics of ATP binding (COM distance & axis angle)
- Pocket torsional stability (χ1) and ligand–protein coupling
- Structural flexibility (Cα RMSF) and cross‑lobe correlation (DCCM)
- Dimensionality reduction (PCA) as a shared‑reference scalar

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the JSONL file that contains all scalar descriptors, per‑replicate statistics, and image file paths.

**Reason:** We need the numeric values and image paths to embed in the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search strings that prioritize the protein name, MD simulation context, and specific analysis methods used.

**Reason:** These queries will drive a focused PubMed search for recent literature.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP axis angle",
    "pocket \u03c71",
    "C\u03b1 RMSF",
    "DCCM",
    "PCA"
  ],
  "user_goal": "Analyze the two 200\u2011ns replicates of the q9y243 protein\u2013ATP holo trajectory extracting scalar dynamics descriptors.",
  "protein_name": "q9y243",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve up to 20 recent references that match the generated queries.

**Reason:** We need up-to-date literature to contextualise the findings.

**Parameters:**
```json
{
  "query": "q9y243 AND (ATP AND \"molecular dynamics\" OR \"protein\u2011ligand dynamics\" OR \"RMSF\" OR \"DCCM\" OR \"PCA\")",
  "max_results": 20,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a self‑contained HTML report that embeds all analysis visualisations, key statistics, and the literature references.

**Reason:** The final deliverable requested by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

