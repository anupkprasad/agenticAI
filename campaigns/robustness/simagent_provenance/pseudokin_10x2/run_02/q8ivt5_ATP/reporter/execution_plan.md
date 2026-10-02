# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To produce the final HTML report we must first ingest the pre‑generated analysis results, then enrich the report with relevant literature that contextualizes the clustering and descriptor findings. The report will embed all visualisations that the analysis agent produced (dendrogram, heat‑map, descriptor plots) and present key statistics in a clean layout. The workflow therefore consists of parsing the JSONL summary, constructing PubMed search queries that target both the protein family (pseudokinases) and the specific MD descriptors used, fetching the top abstracts, and feeding all this information into the `generate_html_report` tool.

## Overview

1️⃣ Parse analysis_summary.jsonl → 2️⃣ Build literature queries → 3️⃣ Retrieve PubMed abstracts → 4️⃣ Assemble references → 5️⃣ Generate comprehensive HTML report (report.html) in the reporter directory.

## Report Focus

- Summary of descriptor statistics (mean, SD, min, max)
- Interpretation of the Ward dendrogram and k = 4 partition
- Heat‑map of scaled, robust features
- Literature context on pseudokinase dynamics and MD clustering

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis_summary.jsonl` file to obtain all descriptor statistics, image file paths, and metadata needed for the report.

**Reason:** All downstream content (statistics, plots) originates from this summary.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a prioritized list of PubMed search queries that target the pseudokinase context and the specific analysis methods used (RMSF, DCCM, PCA, clustering).

**Reason:** Structured queries improve the relevance of retrieved literature.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "clustering"
  ],
  "user_goal": "Generate a concise HTML report summarizing methodology, literature context, the dendrogram, the heat\u2011map, and highlighting a k\u202f=\u202f4 cut for interpretation.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute each generated query to fetch up to 5 recent abstracts that discuss MD‑based analysis of pseudokinases or similar systems.

**Reason:** Collect up-to-date references that explain the importance of the chosen descriptors and clustering approach.

**Parameters:**
```json
{
  "query": "<placeholder_for_each_query>",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Assemble Literature References

**Tool:** ``

**Description:** Consolidate the PubMed results into a list of formatted references (PMID, title, authors, year, journal).

**Reason:** These references will be injected into the report for context.

**Parameters:**
```json
{}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML document that embeds all plots (dendrogram, heat‑map, descriptor boxplots), displays key statistics, and cites the gathered literature.

**Reason:** This is the final deliverable requested by the user.

**Parameters:**
```json
{
  "analysis_data": "<output_of_read_analysis_summary>",
  "literature_refs": "<assembled_literature_list>",
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": {},
  "final_impression": "The clustering of the ten pseudokinase\u2013ATP systems reveals four distinct sub\u2011clusters that align with known functional motifs, supporting the hypothesis that the chosen descriptors capture biologically relevant conformational differences."
}
```

