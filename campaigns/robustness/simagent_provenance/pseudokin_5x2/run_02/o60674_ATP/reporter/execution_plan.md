# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report requires a single‑simulation HTML page that integrates the metrics already computed in `analysis_summary.jsonl` with a concise literature context. We will (1) read the JSONL file to retrieve all analysis statistics and image paths, (2) generate targeted PubMed queries based on the protein names and the analysis methods performed, (3) fetch recent literature references that address ATP‑binding pseudokinase dynamics, and (4) produce a comprehensive HTML report embedding the visualisations and key statistics while citing the retrieved literature.

## Overview

Generate a single‑simulation HTML report for the JAK2‑ATP holo complex by pulling the pre‑computed analysis results, adding relevant literature references, and compiling everything into a clean, professional web page.

## Report Focus

- ATP pocket stability and ligand–protein distance dynamics
- Consensus residue‑level flexibility (RMSF) and inter‑residue correlations (DCCM)
- Torsion and dihedral PCA signatures distinguishing the five pseudokinase systems

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the pre‑generated `analysis_summary.jsonl` file to obtain all analysis metrics, statistics, and paths to visualisation images.

**Reason:** Need to load the analysis data that will be displayed in the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that focus on ATP‑binding pseudokinase dynamics and the specific analysis techniques applied.

**Reason:** Produce focused PubMed queries to retrieve high‑impact literature relevant to the analysis.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DCCM",
    "torsions",
    "dihedral PCA"
  ],
  "user_goal": "Analyze ATP binding dynamics and compare pocket stability across five pseudokinase ATP holo complexes.",
  "protein_name": "JAK2",
  "analysis_stats": {
    "RMSF": {
      "mean": 0.8,
      "max": 1.5
    }
  }
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute a PubMed search using the highest‑priority query to gather recent studies on ATP‑binding pseudokinases and MD analysis.

**Reason:** Obtain contemporary literature that provides context for the observed dynamics.

**Parameters:**
```json
{
  "query": "JAK2 ATP binding pseudokinase molecular dynamics",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds the analysis images, displays key statistics, and cites the retrieved literature.

**Reason:** Produce the final user deliverable in the required directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

