# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user has already run all MD analyses and produced a consolidated summary file `analysis/analysis_summary.jsonl`.  The goal of this workflow is to transform that data into a polished, self‑contained HTML report.  The report will embed all plots, display key statistics in cards, and provide literature context.  Because the summary file already contains image paths, there is no need to read the images manually; the report generator will handle embedding.  To add scientific context we generate PubMed queries tailored to the protein family and analysis methods, fetch the top results, and feed the references to the report generator.

## Overview

1. Load `analysis_summary.jsonl`. 2. Generate PubMed search queries based on the analysis types and protein context. 3. Retrieve relevant literature. 4. Produce a comprehensive HTML report (`report.html`) in the reporter directory, embedding all visualizations and key statistics.

## Report Focus

- Dynamics descriptors and their variability across replicates
- Consensus ligand pocket behaviour
- Inter‑protein residue correlations (DCCM)
- Torsional sampling and dihedral PCA
- Structural context from recent literature

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to obtain all analysis metrics, statistics, and image paths.

**Reason:** We need the full analysis data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Search Queries

**Tool:** `generate_literature_queries`

**Description:** Create prioritized PubMed queries using the analysis types and the protein name.

**Reason:** To produce context‑aware literature searches that focus on the protein family and the specific analyses performed.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DCCM",
    "Torsion",
    "Pocket distance",
    "Dihedral PCA"
  ],
  "user_goal": "For each of the 20 holo protein\u2013ATP PDBs analyze the two existing 200 ns MD trajectories ...",
  "protein_name": "Pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve up to 10 relevant PubMed articles for each generated query.

**Reason:** Collect recent, high‑impact literature for inclusion in the report.

**Parameters:**
```json
{
  "query": "Pseudokinase AND MD simulation AND RMSF",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Collect References

**Tool:** ``

**Description:** Aggregate all unique PubMed citations from the search results into a list of references.

**Reason:** These references will be passed to the report generator for inclusion in the literature section.

**Parameters:**
```json
{}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained report embedding all plots, statistics, and literature.

**Reason:** The final deliverable is a professional HTML file with all required visualisations and insights.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

