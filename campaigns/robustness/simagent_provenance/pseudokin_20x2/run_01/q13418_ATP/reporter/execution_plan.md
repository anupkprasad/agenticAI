# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis_summary.jsonl contains all required statistics and image paths, so the first step is to load it. To enrich the report with relevant literature, we will query UniProt for the protein’s functional annotations, generate focused PubMed queries using the analysis types and the user goal, and then retrieve the top articles. Finally, the generate_html_report tool will weave the analysis data and literature references into a self‑contained, professional HTML document.

## Overview

1️⃣ Load analysis results
2️⃣ Obtain protein functional context (UniProt)
3️⃣ Generate PubMed search queries
4️⃣ Retrieve literature references
5️⃣ Build comprehensive HTML report

## Report Focus

- Quantitative comparison of ATP binding pocket dynamics
- Structural flexibility and inter‑lobe communication
- Consensus‑based PCA insights

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file for metrics and plot paths.

**Reason:** Need to access all quantitative results and image locations.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Get Protein Functional Annotations

**Tool:** `search_uniprot`

**Description:** Query UniProt for the Q13418 entry to collect functional notes and key literature.

**Reason:** Provides biological context and background references for the report.

**Parameters:**
```json
{
  "query": "Q13418",
  "max_results": 1
}
```

### Step 3: Generate PubMed Queries

**Tool:** `generate_literature_queries`

**Description:** Create tailored PubMed queries based on analysis types and the user’s goal.

**Reason:** Produces prioritized search strings that target relevant literature.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP axis angle",
    "pocket \u03c71",
    "C\u03b1 RMSF",
    "DCCM",
    "PCA dynamics"
  ],
  "user_goal": "Holo Kinase Comparative Dynamics Study",
  "protein_name": "Q13418",
  "analysis_stats": {}
}
```

### Step 4: Search PubMed for Each Query

**Tool:** `search_pubmed`

**Description:** Retrieve the top 5 PubMed entries for each generated query.

**Reason:** Collect recent, peer‑reviewed articles that discuss similar analyses or findings.

**Parameters:**
```json
{
  "query": "{{query}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML document embedding analysis images, key statistics, and literature references.

**Reason:** Produces the final deliverable that satisfies the user’s goal.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_data}}",
  "literature_refs": "{{literature_refs}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

