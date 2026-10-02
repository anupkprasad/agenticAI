# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The per‑simulation report requires parsing the JSONL summary to obtain all metrics, plots and file paths, optionally augmenting it with literature context, and then rendering a single self‑contained HTML page.  The workflow is deterministic, uses only the provided tools, and follows the path guidelines strictly.

## Overview

1️⃣ Read and parse the per‑simulation analysis summary. 2️⃣ (Optional) Generate targeted PubMed queries and fetch relevant literature. 3️⃣ Feed the parsed data, literature references, and plot image paths into the report generator to produce a professional, fully embedded HTML report named `report.html` in the reporter directory.

## Report Focus

- ATP–pocket interaction dynamics
- Global conformational flexibility (RMSF, DCCM, dihedral PCA)

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to collect all computed descriptors, statistics, and image paths for this simulation.

**Reason:** Load all analysis outputs needed for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create prioritized PubMed search queries based on the protein name, analysis types performed, and the user’s hypothesis.

**Reason:** Provide relevant literature search terms that focus on both the system (KSR2) and the specific dynamics descriptors.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP_COM_distance",
    "ATP_orientation",
    "\u03c71_angles",
    "RMSF",
    "DCCM",
    "dihedral_PCA"
  ],
  "user_goal": "Rephrase Goal for the Analysis \u2192 Reporter Workflow",
  "protein_name": "KSR2",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve recent articles and abstracts that match the top priority queries.

**Reason:** Obtain concise, up‑to‑date references to contextualise the findings.

**Parameters:**
```json
{
  "query": "KSR2 ATP binding dynamics",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, fully embedded HTML report named `report.html` that includes all plots, key statistics, and literature references.

**Reason:** Produce the final deliverable for this simulation.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

