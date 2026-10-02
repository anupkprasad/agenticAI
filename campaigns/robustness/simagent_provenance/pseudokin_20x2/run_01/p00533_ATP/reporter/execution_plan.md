# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user wants a single‑simulation HTML report that contains all analysis plots, descriptor statistics, and a brief literature context for EGFR ATP binding dynamics. The analysis data are already stored in `analysis/analysis_summary.jsonl`. We will first parse that file, then generate a set of PubMed search queries tailored to EGFR MD studies, run a PubMed search to retrieve recent references, and finally create a comprehensive HTML report that embeds the plots and cites the literature.

## Overview

1️⃣ Parse analysis results from `analysis_summary.jsonl`. 2️⃣ Create focused PubMed queries using the protein name, simulation context, and analysis types. 3️⃣ Retrieve up to three recent papers for each query. 4️⃣ Assemble all information and invoke `generate_html_report` to produce `report.html` with embedded figures, statistics cards, and a short literature summary.

## Report Focus

- EGFR ATP binding pocket dynamics over 200 ns
- Comparative descriptor analysis between rep01 and rep02
- Contextualizing findings with recent EGFR MD literature

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the JSONL file containing all descriptor values, statistics, and image paths.

**Reason:** Need the raw analysis data for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search strings that target EGFR, ATP binding, and the specific analysis methods used (RMSF, DCCM, PCA, pocket metrics).

**Reason:** Generate targeted queries to find relevant literature.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "pocket distance",
    "pocket angle"
  ],
  "user_goal": "Analyze the two existing 200\u202fns trajectories for EGFR (p00533) from the directories `rep01` and `rep02` in `/home/akp66103/.../p00533_ATP`. Compute the ten scalar dynamics descriptors and generate a report.",
  "protein_name": "EGFR",
  "analysis_stats": null
}
```

### Step 3: Search PubMed (first query)

**Tool:** `search_pubmed`

**Description:** Query PubMed with the highest‑priority literature query and retrieve up to 3 recent papers.

**Reason:** Collect up to three recent references for inclusion in the report.

**Parameters:**
```json
{
  "query": "{{generated_queries.priority1}}",
  "max_results": 3,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Prepare Literature References

**Tool:** `extract_literature_refs`

**Description:** Extract title, authors, journal, year, and PMID from the PubMed search results to pass to the report generator.

**Reason:** Format references in a way the report generator can consume.

**Parameters:**
```json
{
  "pubmed_results": "{{search_pubmed_output}}"
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report that includes all plots, descriptor statistics, and literature references.

**Reason:** Produce the final deliverable.

**Parameters:**
```json
{
  "analysis_data": "{{read_analysis_summary_output}}",
  "literature_refs": "{{literature_refs}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

