# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The reporter only needs to transform the already‑computed numerical and visual data from the analysis_summary.jsonl into a polished HTML document.  The workflow therefore begins by parsing the summary file, augments the content with relevant literature retrieved from PubMed, and finally invokes the report generator.  No additional analysis is performed, keeping the execution deterministic and reproducible.

## Overview

1️⃣ Parse `analysis_summary.jsonl` to obtain statistics, feature tables, and image paths. 2️⃣ Generate a set of targeted PubMed queries using the protein name, the performed analyses, and the user goal. 3️⃣ Execute PubMed searches to retrieve a concise bibliography. 4️⃣ Assemble the collected data and literature into a single HTML report (`report.html`) that is placed automatically in the `/home/.../p52333_ATP/reporter/` directory.

## Report Focus

- ATP‑binding pocket dynamics in JAK3
- Consensus pocket‑based scalar descriptors
- Clustering of replica metrics
- Literature context for JAK3 ATP binding

## Execution Steps (7 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load all entries, feature values, and plot paths from the JSONL file produced by the analysis agent.

**Reason:** The analysis data (means, stds, images) is required for the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search strings that prioritize the JAK3 protein and the specific analyses performed.

**Reason:** Structured queries ensure we retrieve context‑relevant literature without flooding the report.

**Parameters:**
```json
{
  "analysis_types": [
    "COM distance",
    "Orientation angle",
    "Chi1 angles",
    "RMSF",
    "DCCM",
    "PCA"
  ],
  "user_goal": "Compute scalar descriptors for the ATP\u2011binding pocket of JAK3 and present clustering results.",
  "protein_name": "JAK3",
  "analysis_stats": null
}
```

### Step 3: Search PubMed (query 1)

**Tool:** `search_pubmed`

**Description:** Retrieve the top 5 articles for the first generated query.

**Reason:** Gather recent, high‑impact references that discuss JAK3 ATP‑binding dynamics.

**Parameters:**
```json
{
  "query": "<first_query_from_step_2>",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Search PubMed (query 2)

**Tool:** `search_pubmed`

**Description:** Retrieve the top 5 articles for the second generated query.

**Reason:** Cover methodological literature (e.g., DCCM, PCA in kinase MD).

**Parameters:**
```json
{
  "query": "<second_query_from_step_2>",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 5: Search PubMed (query 3)

**Tool:** `search_pubmed`

**Description:** Retrieve the top 5 articles for the third generated query.

**Reason:** Add supplementary context (e.g., consensus pocket analysis, side‑chain χ1 studies).

**Parameters:**
```json
{
  "query": "<third_query_from_step_2>",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 6: Compile Literature References

**Tool:** `none`

**Description:** Flatten the PubMed search results into a single list of references, removing duplicates.

**Reason:** The report generator expects a list of reference objects.

**Parameters:**
```json
{}
```

### Step 7: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds all images, displays key statistics, and cites the literature.

**Reason:** Deliver the final, user‑friendly scientific report.

**Parameters:**
```json
{
  "analysis_data": "<output_of_step_1>",
  "literature_refs": "<compiled_references_from_step_5>",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

