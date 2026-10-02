# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To produce the final per‑simulation HTML report we must first read the analysis summary produced by the Analysis Agent.  From this data we obtain the 20 × 10 feature matrix, the dendrogram/heat‑map image paths, and the scalar statistics required for the report.  The report should also contain concise literature context; we generate PubMed queries based on the analysis types, fetch the top references, and embed them in the report.  Finally, we generate a single comprehensive HTML report that will be written to `report.html` in the reporter directory.

## Overview

1️⃣ Read the `analysis_summary.jsonl` file. 2️⃣ Create PubMed search queries that target the protein, the MD analysis, and the study objective. 3️⃣ Retrieve the most relevant literature entries. 4️⃣ Generate a self‑contained HTML report that embeds all images, shows key statistics, and lists literature references.

## Report Focus

- Statistical clustering of the 20 pseudokinase‑ATP systems
- Key dynamic descriptors and their averages
- Literature context linking ATP‑binding dynamics to pseudokinase regulation

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to extract all computed descriptors, statistics, and image file paths.

**Reason:** We need the raw data and visualisation paths for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries

**Tool:** `generate_literature_queries`

**Description:** Build a list of PubMed queries that prioritise protein‑MD simulation context, specific descriptors, and the user objective.

**Reason:** To generate relevant literature search terms that align with the analysis performed.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "pocket \u03c71",
    "C\u03b1 RMSF",
    "DCCM",
    "dihedral\u2011PCA"
  ],
  "user_goal": "Load the two 200\u2011ns production trajectories for each of the 20 protein\u2013ATP holo systems, compute the ten scalar dynamics descriptors, average the results, cluster the systems, and produce a comprehensive HTML report that includes clustering, heat\u2011map, dendrogram, and concise literature context.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed for Top Query

**Tool:** `search_pubmed`

**Description:** Execute a PubMed search using the highest‑priority query returned by the literature query generator and collect the top results.

**Reason:** Provide up‑to‑date, high‑quality literature references to contextualise the findings.

**Parameters:**
```json
{
  "query": "{{top_query}}",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a single comprehensive HTML report that embeds all analysis images, presents key statistics cards, and lists the retrieved literature references.

**Reason:** Final deliverable – a self‑contained HTML report for the reporter directory.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_summary}}",
  "literature_refs": "{{pubmed_results}}",
  "report_type": "comprehensive",
  "output_file": "report.html",
  "enriched_prompt": "Generate a comprehensive scientific report summarising the clustering, heat\u2011map, dendrogram, and literature context for the 20 pseudokinase\u2011ATP holo systems."
}
```

