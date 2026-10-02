# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The analysis of the 200‑ns trajectories for all 37 human protein‑ATP holo structures has already produced a comprehensive `analysis_summary.jsonl` containing per‑system descriptors, cluster assignments, heatmap and dendrogram image paths, and other summary statistics. The next step is to ingest this file, format the data into a structured dictionary, and feed it to the `generate_html_report` tool which will create a self‑contained `report.html` with embedded images, key statistics cards, and a professional layout. Since the user explicitly requested literature context for each protein, the plan includes a literature‑search phase that will build a list of PubMed queries for each protein, retrieve recent articles, and embed the most relevant references in the report. No other tools are invoked, keeping the workflow deterministic and focused on producing the final report.

## Overview

1. Read the analysis summary file. 2. Generate PubMed queries per protein and retrieve short abstracts. 3. Feed the parsed data and literature references to `generate_html_report` to create the final HTML report in `reporter/`.

## Report Focus

- Ward hierarchical clustering and k=4 cut interpretation
- Key descriptor statistics (mean, std, min, max)
- Literature context for each protein

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to extract descriptor values, image paths, and cluster information.

**Reason:** The analysis data is required to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries (Optional)

**Tool:** `generate_literature_queries`

**Description:** Create protein‑specific PubMed search queries using the provided `generate_literature_queries` logic and retrieve relevant literature.

**Reason:** Literature context enriches the report and satisfies the user’s requirement for brief references per protein.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "pocket \u03c71",
    "RMSF",
    "DCCM",
    "dihedral PCA entropy"
  ],
  "user_goal": "Summarise clustering of 37 human protein\u2011ATP holo structures with literature context for each protein.",
  "protein_name": "Placeholder",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the generated queries to fetch article metadata and abstracts.

**Reason:** Retrieve up-to-date references for inclusion in the report.

**Parameters:**
```json
{
  "query": "Placeholder",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report from the analysis data and literature references.

**Reason:** Produce the final deliverable in the `reporter/` directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": null,
  "final_impression": null,
  "pdb_data": null,
  "enriched_prompt": null
}
```

