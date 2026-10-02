# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis summary already contains all quantitative descriptors and the associated plot paths. We first load this data, then optionally enrich it with literature context via PubMed searches. Finally, we feed the combined data into `generate_html_report` to produce a self‑contained HTML file with embedded images, key statistics cards, and a concise literature synthesis.

## Overview

1️⃣ Load `analysis_summary.jsonl` → 2️⃣ Generate literature queries → 3️⃣ Fetch top PubMed references → 4️⃣ Produce a comprehensive per‑simulation HTML report.

## Report Focus

- ATP COM distance (mean & SD)
- ATP orientation (mean & SD)
- Pocket χ₁ (mean & SD)
- Consensus‑mapped Cα RMSF (mean & SD)
- N‑lobe↔C‑lobe DCCM mean
- Shared‑reference dihedral PCA scalar

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to extract dynamic descriptors and image paths.

**Reason:** We need the full dataset for reporting.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search strings based on protein, MD methods, and analysis outputs.

**Reason:** Targeted queries improve relevance of retrieved literature.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "pocket \u03c71",
    "C\u03b1 RMSF",
    "N\u2011lobe\u2194C\u2011lobe DCCM",
    "dihedral PCA"
  ],
  "user_goal": "compute dynamic descriptors for ATP holo states and cluster the systems",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed – Priority 1

**Tool:** `search_pubmed`

**Description:** Retrieve recent articles on pseudokinase MD simulations and ATP binding dynamics.

**Reason:** First priority query is likely to yield the most directly relevant papers.

**Parameters:**
```json
{
  "query": "pseudokinase AND MD simulation AND ATP binding",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Search PubMed – Priority 2

**Tool:** `search_pubmed`

**Description:** Retrieve literature on dynamic metrics (RMSF, DCCM) in pseudokinases.

**Reason:** Second priority query supplements context around specific analyses.

**Parameters:**
```json
{
  "query": "pseudokinase AND RMSF AND DCCM",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, self‑contained HTML report embedding all plots and key statistics.

**Reason:** This is the final deliverable for the per‑simulation report.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

