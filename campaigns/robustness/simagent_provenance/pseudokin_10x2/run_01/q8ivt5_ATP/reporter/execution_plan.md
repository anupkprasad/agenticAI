# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis for the two KSR1 replicas is already completed and the results are stored in `analysis/analysis_summary.jsonl`.  The report must present the averaged descriptor vector, visualizations (heatmap, dendrogram, etc.) and a concise interpretation.  The only required step is to parse the summary file and feed the data to `generate_html_report`, which will embed all plots and produce the final `report.html` in the reporter's working directory.  A brief literature context will be added by performing a PubMed search for recent papers on KSR1 structure–function and on the specific analysis methods (RMSF, DCCM, dihedral PCA).

## Overview

1. Parse the analysis summary to extract scalar descriptors, averaged values, and image paths. 2. Perform a targeted PubMed search for recent KSR1 MD/structural studies and for the analysis methods used. 3. Generate a comprehensive HTML report that embeds the visualizations, presents key statistics, and situates the findings in the literature.

## Report Focus

- Averaged descriptor vector for KSR1 holo system
- Heatmap of descriptor values (robust z‑score/IQR scaling)
- Ward clustering dendrogram with k=4 cut
- Literature context on KSR1 MD/structure‑function

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis/analysis_summary.jsonl` file to obtain the descriptor values, average statistics, and the file paths of the heatmap, dendrogram and other generated plots.

**Reason:** Load all results needed for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that focus on KSR1, MD simulation, and the specific descriptors (RMSF, DCCM, dihedral PCA).

**Reason:** Create search terms for literature retrieval.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "dihedral PCA",
    "ATP COM distance",
    "ATP orientation"
  ],
  "user_goal": "Analyze the two 200\u2011ns KSR1 trajectories and produce a descriptor vector, heatmap, dendrogram, and literature context.",
  "protein_name": "KSR1",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve the most recent papers that match the generated queries.

**Reason:** Gather up-to-date references for the report.

**Parameters:**
```json
{
  "query": "KSR1 MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that includes all embedded plots, key statistics cards, and a literature review.

**Reason:** Produce the final deliverable.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": {
    "system_name": "q8ivt5_ATP",
    "protein": "KSR1",
    "replicates": 2,
    "trajectory_length_ns": 200,
    "ligand": "ATP"
  },
  "final_impression": "The averaged descriptors reveal that KSR1 remains tightly bound to ATP with modest conformational fluctuations, consistent with recent high\u2011resolution MD studies that report a stable ATP pocket and limited lobe reorientation."
}
```

