# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a single‑simulation HTML report that incorporates the quantitative descriptors calculated from the 200‑ns trajectories of ten protein–ATP holo complexes.  The plan must (i) parse the analysis summary, (ii) generate and execute literature searches for contextual references, and (iii) feed both the parsed data and literature citations to the report generator.  All tool invocations are deterministic and use the file names and paths prescribed by the system.

## Overview

1. Load the `analysis_summary.jsonl` file.  2. Produce a set of PubMed queries that target both the protein context (pseudokinases/ATP binding) and the specific descriptors computed.  3. Run PubMed searches for each query and collect a concise list of references.  4. Feed the parsed analysis data and the reference list into `generate_html_report` to create a professionally styled, fully‑embedded HTML report titled `report.html` in the reporter directory.

## Report Focus

- ATP binding pocket dynamics across the ten pseudokinase holo complexes
- Inter‑lobe coordination (N‑ vs C‑lobe DCCM)
- Conformational entropy inferred from dihedral PCA
- Cluster‑based functional grouping and dendrogram interpretation

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains the ten scalar descriptors for each of the ten systems, as well as image file paths for dendrograms and heatmaps.

**Reason:** All subsequent steps require the raw data, statistics, and image paths to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a priority list of PubMed search queries that cover the protein family, ATP‑binding dynamics, and the specific descriptors that were calculated.

**Reason:** Prioritised queries will focus on the most relevant literature and reduce the search space.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM-pocket distance",
    "ATP orientation",
    "pocket \u03c71",
    "C\u03b1\u2011RMSF",
    "N\u2011lobe DCCM",
    "C\u2011lobe DCCM",
    "dihedral PCA entropy"
  ],
  "user_goal": "Analyze the existing 200\u2011ns trajectories (both replicates) for each of the ten protein\u2013ATP holo complexes in /\u2026/p24941_ATP and aggregate the descriptors into a feature table, cluster, and generate a dendrogram and heatmap.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Execute PubMed Searches

**Tool:** `search_pubmed`

**Description:** Run a PubMed search for each generated query, retrieving up to 5 abstracts per query to provide recent, high‑impact context.

**Reason:** Literature citations will be embedded in the report to give the reader a concise background.

**Parameters:**
```json
{
  "query": "{{generated_query}}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Aggregate Literature References

**Tool:** ``

**Description:** Compile the PubMed search results into a flat list of reference objects (title, authors, journal, year, PMID).  The list will be passed to the report generator.

**Reason:** The report tool expects a list of references to display.

**Parameters:**
```json
{}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report named `report.html` that embeds all images, displays the key statistics in cards, and presents the literature references.

**Reason:** This is the final deliverable requested by the user.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_data}}",
  "literature_refs": "{{literature_refs}}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

