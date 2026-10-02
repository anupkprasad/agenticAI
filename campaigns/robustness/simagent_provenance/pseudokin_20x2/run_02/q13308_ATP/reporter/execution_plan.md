# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that pulls together all the scalar descriptors, the MSA and dendrogram visualisations, and contextual literature for each protein. The analysis results are already stored in `analysis/analysis_summary.jsonl`. We will first parse that file, then optionally pull in relevant literature via PubMed, and finally generate a comprehensive HTML report that automatically embeds the images and key statistics.

## Overview

1. Parse the existing JSONL analysis summary. 2. Generate tailored PubMed queries and retrieve a short set of recent references for context. 3. Feed the parsed data and literature references into `generate_html_report`, producing a self‑contained `report.html` in the reporter directory.

## Report Focus

- Dynamics descriptors across the 20 systems
- Comparative structural conservation (MSA & pocket consensus)

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all descriptor statistics, image paths, and metadata.

**Reason:** We need the complete analysis payload (statistics + image locations) to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search strings that focus on the protein name, the MD simulation context, and the specific analysis types performed.

**Reason:** These queries will be used to retrieve concise literature that contextualises the findings.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP-COM distance",
    "ATP-pocket orientation",
    "pocket \u03c71",
    "RMSF",
    "DCCM",
    "dihedral PCA"
  ],
  "user_goal": "For each of the 20 protein\u2013ATP holo trajectories compute dynamics descriptors and produce a comprehensive comparative analysis.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent papers for each query generated above.

**Reason:** We want recent, relevant literature to include in the report.

**Parameters:**
```json
{
  "query": "{{generated_queries}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all analysis plots, displays key statistics, and includes the literature references.

**Reason:** This is the final deliverable the user requested.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_summary_output}}",
  "literature_refs": "{{pubmed_results}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

