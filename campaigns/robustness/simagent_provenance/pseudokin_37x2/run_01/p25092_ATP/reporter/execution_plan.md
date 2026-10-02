# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that summarises all analysis outputs stored in the analysis_summary.jsonl file. The workflow is deterministic: we only need to read the summary, optionally pull in literature context, and then call generate_html_report with the parsed data. No additional preprocessing, simulation or clustering steps are required for the per‑simulation report. The plan below follows the prescribed tool usage and file‑path conventions.

## Overview

1. Read the analysis_summary.jsonl located in the /analysis directory of the current protein‑ATP holo structure. 2. (Optional) Generate a set of PubMed queries that relate the protein name, the analysis methods used, and any striking statistics (e.g., unusually high RMSF). 3. Pass the parsed analysis data to generate_html_report to create a professional, self‑contained report named report.html in the reporter/ subdirectory.

## Report Focus

- Ligand pocket distance and orientation
- Consensus dynamics (RMSF, DCCM, PCA)
- Key scalar descriptors (ATP COM, pocket‑axis, torsion, etc.)

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse analysis_summary.jsonl to retrieve all analysis results, statistics, and paths to visualisation images.

**Reason:** Load the core data that will be embedded in the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries (optional)

**Tool:** `generate_literature_queries`

**Description:** Build PubMed search queries that target the protein and the analysis methods used, to provide context in the final report.

**Reason:** Provide curated literature references to accompany the analysis.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "torsion",
    "contact"
  ],
  "user_goal": "User's goal text from the original instruction",
  "protein_name": "pseudokinase system name (e.g., p25092)",
  "analysis_stats": null
}
```

### Step 3: Search PubMed for Literature

**Tool:** `search_pubmed`

**Description:** Retrieve up to 10 relevant articles for each generated query to populate the literature section of the report.

**Reason:** Obtain up-to-date references for contextual discussion.

**Parameters:**
```json
{
  "query": "generated_query_string",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": null
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds images, displays key statistics, and includes literature references.

**Reason:** Produce the final deliverable that the user can view and share.

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

