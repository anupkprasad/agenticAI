# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The per‑simulation report requires only the analysis results stored in the local `analysis_summary.jsonl` file. These results already contain the image file paths, scalar descriptors, and metadata needed for the HTML output. The `generate_html_report` tool automatically embeds the images and creates the desired layout. To enrich the report with recent literature, a small literature‑search step can be inserted before report generation, but it is optional. The plan therefore reads the summary, optionally pulls a handful of PubMed references relevant to ATP‑binding pseudokinases and MD descriptors, and finally produces the HTML report.

## Overview

1. Parse the analysis summary. 2. (Optional) Retrieve up to five recent PubMed articles for context. 3. Generate a comprehensive HTML report titled `report.html` in the `reporter/` directory, embedding all visualisations and key statistics.

## Report Focus

- Key ATP‑binding pocket metrics (COM distance, orientation, χ1 torsion)
- Consensus RMSF and DCCM insights
- Clustering of pseudokinase dynamics
- Literature context on ATP‑binding flexibility

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing per‑replica metrics, images, and metadata for the current simulation.

**Reason:** We need the analysis data to feed the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Construct a small set of PubMed queries that focus on ATP‑binding pseudokinases and MD descriptor analysis to provide context.

**Reason:** We want a concise literature context for the report.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP binding",
    "RMSF",
    "RMSD",
    "DCCM",
    "torsion analysis"
  ],
  "user_goal": "Analyze ATP\u2011binding dynamics of pseudokinase homologs and relate descriptors to functional flexibility.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve up to 5 recent PubMed abstracts that match the generated queries.

**Reason:** Provide up-to-date literature references in the report.

**Parameters:**
```json
{
  "query": "${generate_literature_queries.output.queries[0]}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create the final HTML report incorporating analysis data, embedded plots, statistics cards, and literature references.

**Reason:** Produce the deliverable in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": "${read_analysis_summary.output}",
  "literature_refs": "${search_pubmed.output.results}",
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": null,
  "final_impression": null,
  "pdb_data": null,
  "enriched_prompt": null
}
```

