# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To produce a concise and informative HTML report, we first need to load the pre‑generated analysis data from `analysis_summary.jsonl`.  From this data we can automatically extract the analysis types performed and the key statistical metrics.  A short literature search (PubMed) will provide context for the observed descriptors and help annotate the report.  Finally, we use `generate_html_report` to stitch the statistics, embedded plots, and literature citations into a professional report.  All output will be written to the dedicated reporter directory with the required filename `report.html`.

## Overview

1️⃣ Read analysis summary  
2️⃣ Generate PubMed queries based on analysis types  
3️⃣ Retrieve relevant literature  
4️⃣ Produce the HTML report

## Report Focus

- Ligand‑pocket COM distance & orientation
- Side‑chain χ1 distribution
- Cα RMSF mapping
- Inter‑lobe DCCM
- Dihedral PCA dynamics

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains the computed metrics, statistics and paths to plot images.

**Reason:** Need access to the results that will populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries

**Tool:** `generate_literature_queries`

**Description:** Create a set of targeted search strings using the analysis types found in the summary.

**Reason:** To identify recent studies that discuss similar descriptors and the pseudokinase system.

**Parameters:**
```json
{
  "analysis_types": [
    "Ligand-pocket COM distance",
    "Ligand orientation",
    "Side\u2011chain \u03c71",
    "C\u03b1 RMSF",
    "DCCM",
    "Dihedral PCA"
  ],
  "user_goal": "Perform all requested analyses on the existing 200\u2011ns trajectories of q8ne28_ATP and report key descriptors",
  "protein_name": "q8ne28",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Query PubMed for literature matching the generated queries and collect titles, abstracts and PMIDs.

**Reason:** Retrieve up to five recent, relevant papers to embed as references in the report.

**Parameters:**
```json
{
  "query": "pseudokinase q8ne28 AND (ligand pocket distance OR RMSF OR DCCM OR PCA) AND simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML file that embeds the plots, displays the key statistics, and cites the literature.

**Reason:** Produce the final deliverable in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": {
    "system_name": "q8ne28_ATP",
    "trajectory_length_ns": 200,
    "replicates": 2
  }
}
```

