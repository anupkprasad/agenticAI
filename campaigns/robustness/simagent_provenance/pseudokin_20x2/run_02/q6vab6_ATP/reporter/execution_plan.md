# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report requires only a single‑simulation analysis.  We first load the detailed metrics and image paths from the JSONL file, then generate targeted PubMed queries to enrich the narrative.  The search results are distilled into a list of formatted references that the report generator will embed.  Finally, we produce a single comprehensive HTML file named `report.html` that automatically embeds all plots, displays key statistics, and includes the literature context.

## Overview

1️⃣ Load analysis data  2️⃣ Generate PubMed queries  3️⃣ Search PubMed & assemble references  4️⃣ Create the HTML report with embedded images and cards.

## Report Focus

- Consensus pocket ATP dynamics (distance & orientation)
- Side‑chain χ1 angle variability
- Cα RMSF patterns across the protein
- Inter‑lobe DCCM correlations
- Entropy of shared dihedral PCA space

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to retrieve all scalar descriptors, statistics, and image file paths.

**Reason:** We need the raw analysis data to drive the report content.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Search Queries

**Tool:** `generate_literature_queries`

**Description:** Create a prioritized list of PubMed queries based on the protein name, the analysis methods performed, and the user hypothesis.

**Reason:** Targeted queries increase the chance of retrieving relevant literature.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "\u03c71 angles",
    "C\u03b1 RMSF",
    "DCCM correlation",
    "dihedral PCA entropy"
  ],
  "user_goal": "Summarise how consensus\u2011pocket dynamics differentiate kinase versus pseudokinase behaviour",
  "protein_name": "q6vab6",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the PubMed searches for each generated query and collect the top 5 abstracts per query.

**Reason:** To obtain recent, peer‑reviewed studies that discuss ATP‑pocket interactions and the specific analytical metrics.

**Parameters:**
```json
{
  "query": "{{generated_query_from_previous_step}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Assemble Literature References

**Tool:** ``

**Description:** Extract title, authors, year, DOI, and abstract from each search result and format them into a list of reference objects.

**Reason:** These references will be passed to the report generator for inclusion in the literature section.

**Parameters:**
```json
{}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that embeds all plots, displays key statistics cards, and includes the literature references.

**Reason:** This is the final deliverable that the user expects.

**Parameters:**
```json
{
  "analysis_data": "{{parsed_analysis_data_from_step1}}",
  "literature_refs": "{{assembled_references}}",
  "report_type": "comprehensive",
  "output_file": "report.html",
  "enriched_prompt": "Generate a comprehensive scientific report for the q6vab6 ATP holo complex, summarising consensus pocket dynamics, lobe correlation, and dihedral entropy."
}
```

