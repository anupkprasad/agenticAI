# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requested a comprehensive, single‑simulation HTML report that links the MD analysis (RMSD, RMSF, Rg, DCCM, DSSP) to recent literature on TITIN activation‑loop conformations and allosteric regulation.  The workflow therefore requires: (1) reading the analysis_summary.jsonl to extract numeric results and image paths; (2) generating PubMed queries that are tailored to TITIN and the specific analyses; (3) retrieving up to 10 recent (last 5 yrs) PubMed abstracts; (4) compiling a short literature reference list; and (5) creating an HTML report that embeds the plots, displays key statistics cards, and cites the selected literature.  All actions are performed with the provided tools, respecting the constraints on tool usage and output filenames.

## Overview

The plan will parse the analysis summary, search PubMed for up to ten relevant articles, collect their titles and DOIs, and then generate a self‑contained `report.html` that visually presents the simulation data and contextualizes it with recent experimental/computational findings on TITIN’s activation‑loop and allosteric mechanisms.

## Report Focus

- TITIN activation‑loop conformations
- Allosteric regulation mechanisms

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all analysis statistics and image paths.

**Reason:** Need the numeric results and plot locations to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that focus on TITIN, activation‑loop, allosteric regulation, and the specific analysis methods (RMSD, RMSF, DCCM, DSSP).

**Reason:** Obtain targeted queries for PubMed that match the user’s scientific focus.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DCCM",
    "DSSP"
  ],
  "user_goal": "Analyze TITIN activation\u2011loop conformations and allosteric regulation.",
  "protein_name": "TITIN",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the generated queries to retrieve recent literature on TITIN’s activation‑loop and allosteric regulation.

**Reason:** Collect up to ten recent, high‑impact papers to cite in the report.

**Parameters:**
```json
{
  "query": "{{PLACEHOLDER_QUERY_FROM_PREVIOUS_STEP}}",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Compile Literature References

**Tool:** `none`

**Description:** Extract titles, authors, journal names, publication years, DOIs, and PubMed IDs from the PubMed results, assembling a list suitable for the report.

**Reason:** Prepare a concise reference list for inclusion in the HTML.

**Parameters:**
```json
{}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all analysis plots, shows key statistics cards, and includes the compiled literature references.

**Reason:** Produce the final deliverable requested by the user.

**Parameters:**
```json
{
  "analysis_data": "{{RESULT_FROM_READ_ANALYSIS_SUMMARY}}",
  "literature_refs": "{{COMPILED_REFERENCE_LIST}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

