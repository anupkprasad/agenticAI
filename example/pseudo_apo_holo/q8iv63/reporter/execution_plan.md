# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a comprehensive per‑trajectory report that includes all of the analyses already performed in the `analysis_summary.jsonl` file.  To enrich the report with context, we will (1) read and parse the summary file, (2) extract the list of analyses and any key statistics, (3) generate PubMed search queries that target the protein’s activation‑loop and allosteric regulation as well as the specific MD observables, (4) retrieve a small set of relevant literature, and finally (5) create an HTML report that embeds the plots, displays the statistics cards, and cites the retrieved papers.  All steps use the supplied tools and avoid any multi‑simulation or HPC actions.

## Overview

1) Load analysis results  
2) Create literature search queries  
3) Fetch key literature  
4) Generate a single‑simulation HTML report (report.html)  
All files are written to the reporter's output directory and the report is fully self‑contained.

## Report Focus

- Activation‑loop conformations
- Allosteric regulation

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing RMSD, RMSF, Rg, DCCM, DSSP statistics and image paths.

**Reason:** We need the raw data to populate the report and to build literature queries.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Extract Analysis Metadata

**Tool:** ``

**Description:** From the parsed summary, build a list of analysis types and a dictionary of mean/max values for each.

**Reason:** These values are required to construct targeted PubMed queries.

**Parameters:**
```json
{}
```

### Step 3: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed queries that prioritize the protein name (ERBB3, VRK3, MLKL, TITIN), MD simulation context, analysis methods, and the user hypothesis on activation‑loop and allostery.

**Reason:** These queries will be used to fetch up-to-date papers that contextualize the simulation data.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "Rg",
    "DCCM",
    "DSSP"
  ],
  "user_goal": "Focus on activation\u2011loop conformations and allosteric regulation, correlating simulation findings with literature.",
  "protein_name": "ERBB3",
  "analysis_stats": {
    "RMSD": {
      "mean": 1.5,
      "max": 3.0
    }
  }
}
```

### Step 4: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the top query for each protein and retrieve abstracts and citation counts.

**Reason:** Obtain literature references that will be cited in the report.

**Parameters:**
```json
{
  "query": "ERBB3 MD simulation activation loop allostery",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a professional HTML file named report.html that embeds all plots, displays key statistics, and lists the retrieved literature.

**Reason:** This is the final deliverable required by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

