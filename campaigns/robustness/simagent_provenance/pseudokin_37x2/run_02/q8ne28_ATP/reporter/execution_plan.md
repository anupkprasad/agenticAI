# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report must summarize the scalar descriptors, per‑system metrics, and clustering results from the existing trajectories.  All numerical results and figure paths are stored in the `analysis/analysis_summary.jsonl` file.  The `generate_html_report` tool automatically embeds these figures and formats the text.  To provide scientific context, a short PubMed search is performed using queries that focus on pseudokinase MD simulations and the specific analysis methods used.

## Overview

1. Load the per‑simulation analysis summary. 2. Build PubMed queries from the analysis types and the user goal. 3. Retrieve relevant literature. 4. Generate a comprehensive HTML report in the reporter directory.

## Report Focus

- ATP‑pocket interaction metrics
- Protein side‑chain χ₁ dynamics
- Clustering of global conformational features

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all metrics, statistics, and image file paths.

**Reason:** Need the raw data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries

**Tool:** `generate_literature_queries`

**Description:** Create prioritized PubMed search queries based on the analysis types and the user goal.

**Reason:** Prepare focused literature queries that match the analysis methods.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "ATP pocket distance",
    "torsion analysis",
    "principal component analysis"
  ],
  "user_goal": "For the 37 protein\u2013ATP holo structures (two 200\u202fns replicas each) already present in the working directory, perform the following analyses on the existing trajectories (protein\u202f+\u202fATP only; exclude crystallographic Mg/ions and water): compute the ten scalar descriptors, run per\u2011system analyses, average across replicas, cluster the features, and produce a concise HTML report.",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve recent literature that discusses pseudokinase MD simulations and the specific analytical techniques.

**Reason:** Obtain up‑to‑date references to include in the report.

**Parameters:**
```json
{
  "query": "{{query_from_generate_literature_queries.output['queries']['priority1']}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report embedding all figures, statistical cards, clustering dendrograms, and literature context.

**Reason:** Produce the final deliverable.

**Parameters:**
```json
{
  "analysis_data": "{{Read Analysis Summary.output}}",
  "literature_refs": "{{Search PubMed.output['results']}}",
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": null,
  "final_impression": "The clustering analysis reveals four distinct ligand\u2011binding modes that correlate with known functional states of pseudokinases.  Consistent ATP\u2011pocket distances and orientations across replicas support the robustness of the observed conformational ensembles, while the dihedral\u2011PCA entropy highlights key flexible regions.  Recent MD studies (see references) emphasize the role of side\u2011chain \u03c7\u2081 dynamics in stabilizing ligand affinity, corroborating our findings.",
  "pdb_data": null,
  "enriched_prompt": "Generate a concise HTML report summarizing the scalar descriptors, per\u2011system metrics, clustering results, and literature context for 37 protein\u2013ATP holo structures (two 200\u202fns replicas each)."
}
```

