# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user’s goal is to produce a single‑simulation HTML report that embeds all analysis outputs (distance, angle, χ1, RMSF, DCCM, PCA) and provides brief literature context for the studied pseudokinase–ATP complexes. The `analysis_summary.jsonl` file contains all scalar descriptors and the paths to the diagnostic plots. To satisfy the requirement of literature context we will generate a set of PubMed queries tailored to the analysis types and the protein family, fetch a handful of relevant papers, and pass those references to the report generator. This approach keeps the workflow deterministic and lightweight while fulfilling the user’s specification for a comprehensive, modern‑looking report.

## Overview

1. Parse the analysis summary. 2. Create PubMed queries for pseudokinase MD studies and descriptor methods. 3. Retrieve the most recent literature and collect citations. 4. Generate an HTML report that embeds all plots, displays key statistics, and lists the literature references.

## Report Focus

- ATP pocket geometry (distance & angle)
- Side‑chain rotamer behaviour (χ1)
- Lobe‑lobe correlation (DCCM)
- Global dynamics (PCA)
- Clustering of pseudokinase conformational states

## Execution Steps (6 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the per‑system descriptor tables, statistics, and image file paths from the JSONL file.

**Reason:** We need the complete dataset and plot locations to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Produce PubMed search queries that target pseudokinase MD simulations and the specific descriptors used.

**Reason:** These queries will fetch relevant MD and descriptor papers for the literature section.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DCCM",
    "PCA",
    "pocket distance",
    "pocket angle"
  ],
  "user_goal": "Analyze the ATP pocket dynamics and inter\u2011lobe correlations in 20 pseudokinase\u2013ATP holo complexes over 200 ns trajectories, then cluster the systems and provide literature context.",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Search PubMed for Each Query

**Tool:** `search_pubmed`

**Description:** Execute each generated query and collect up to 5 recent abstracts per query.

**Reason:** Retrieve concrete references that discuss MD analysis of pseudokinases.

**Parameters:**
```json
{
  "query": "pseudokinase MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Search PubMed for Secondary Query

**Tool:** `search_pubmed`

**Description:** Execute the second priority query to broaden coverage.

**Reason:** Add references that specifically mention PCA‑based dynamics of pseudokinases.

**Parameters:**
```json
{
  "query": "pseudokinase dynamics PCA",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 5: Aggregate Literature References

**Tool:** ``

**Description:** Flatten the two PubMed result sets into a single list of reference dictionaries (title, authors, year, PMID).

**Reason:** The report generator expects a flat list of citation objects.

**Parameters:**
```json
{}
```

### Step 6: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional, embedded‑image report that presents the clustering dendrogram, heat‑map, and key descriptor statistics, and includes the collected literature citations.

**Reason:** This is the final deliverable the user requested.

**Parameters:**
```json
{
  "analysis_data": "<PARSED_ANALYSIS_DATA_FROM_STEP_1>",
  "literature_refs": "<COLLECTED_REFERENCES_FROM_STEP_5>",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

