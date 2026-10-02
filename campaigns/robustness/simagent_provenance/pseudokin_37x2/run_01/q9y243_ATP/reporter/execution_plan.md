# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The goal is to produce a single‐simulation, comprehensive HTML report that embeds all analysis plots and highlights key statistics while providing concise literature context. We first load the per‑system analysis data from `analysis_summary.jsonl`. Next, we automatically generate PubMed queries that focus on the protein name, the MD analysis methods performed, and the user’s objective. For each query we retrieve a small set of relevant articles, collect their metadata, and use these as literature references in the report. Finally, we call `generate_html_report` to build the fully‑styled document, automatically embedding all images and statistics, and saving it as `report.html` in the reporter directory.

This workflow uses only the permitted tools, avoids inventing placeholder files or paths, and keeps the output deterministic across runs.

## Overview

1. Read analysis results. 2. Generate PubMed queries from the analysis types and protein context. 3. Retrieve top 3 references per query. 4. Assemble a unified list of literature references. 5. Generate the HTML report, embedding images, stats, and the literature section.

## Report Focus

- ATP binding metrics (distance, orientation, χ1)
- Protein dynamic descriptors (RMSF, DCCM, PCA entropy)
- Literature context linking pseudokinase dynamics to functional regulation

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain per‑system statistics, metric values, and image paths.

**Reason:** We need the raw analysis data to build the report and to identify which metrics were calculated.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries based on the protein name, the set of analysis methods, and the user goal.

**Reason:** Providing tailored queries increases the relevance of the literature we retrieve.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "RMSD",
    "\u03c71",
    "distance"
  ],
  "user_goal": "Analyze ATP binding dynamics in pseudokinase systems",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Search PubMed for Each Query

**Tool:** `search_pubmed`

**Description:** For every query produced, retrieve the top 3 PubMed results (with abstracts) to build a set of contextual references.

**Reason:** We limit to recent, high‑impact studies to keep the report focused.

**Parameters:**
```json
{
  "query": "<placeholder>",
  "max_results": 3,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Collect Literature References

**Tool:** ``

**Description:** Aggregate the PubMed search results into a single list, removing duplicates and formatting for the report.

**Reason:** The report tool accepts a list of reference objects.

**Parameters:**
```json
{}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create the final comprehensive report, embedding images, statistics, and literature references.

**Reason:** This is the final deliverable requested by the user.

**Parameters:**
```json
{
  "analysis_data": "<analysis_data_from_step_1>",
  "literature_refs": "<literature_refs_from_step_4>",
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": null,
  "final_impression": null,
  "pdb_data": null,
  "enriched_prompt": "Generate a comprehensive scientific report for a pseudokinase ATP holo trajectory, summarizing ATP binding metrics, protein dynamics, and contextual literature."
}
```

