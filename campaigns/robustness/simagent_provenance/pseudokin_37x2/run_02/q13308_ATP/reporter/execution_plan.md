# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requires a concise, self‑contained HTML report summarising the clustering, descriptor statistics, and literature context for a single MD simulation run.  The analysis results are already available in `analysis/analysis_summary.jsonl`; therefore the report generation workflow consists of three deterministic steps: 1) parse the summary file, 2) retrieve a small set of relevant literature to provide context, and 3) generate the HTML report using the supplied tool.  No additional preprocessing or simulation steps are needed, and the report will be stored in the dedicated `reporter/` directory.

## Overview

The workflow reads the per‑simulation analysis summary, queries PubMed for recent literature on ATP‑bound pseudokinases and the specific descriptors used, and then produces a professional HTML report containing embedded plots, key statistics, and literature references.

## Report Focus

- ATP binding dynamics and orientation
- Pocket flexibility and χ1 rotamer distributions
- Structural correlation between N‑lobe and C‑lobe motions
- Consensus‑based RMSF and DCCM clustering

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the JSONL file containing all computed descriptors, clustering results, and image paths.

**Reason:** All downstream steps need the analysis data.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create focused PubMed search queries based on the protein context and analysis methods.

**Reason:** To provide up‑to‑date scientific context for the reported metrics.

**Parameters:**
```json
{
  "analysis_types": [
    "ATP COM distance",
    "ATP orientation",
    "pocket \u03c71",
    "C\u03b1 RMSF",
    "DCCM",
    "dihedral PCA entropy"
  ],
  "user_goal": "Analyze ATP dynamics and pocket flexibility in pseudokinase holo complexes.",
  "protein_name": "pseudokinase",
  "analysis_stats": {
    "ATP COM distance": {
      "mean": 5.2,
      "max": 9.8
    },
    "C\u03b1 RMSF": {
      "mean": 1.1,
      "max": 3.4
    }
  }
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the top two literature queries to retrieve article metadata and abstracts.

**Reason:** Collect recent studies that discuss similar descriptors or systems.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding dynamics molecular dynamics",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create the final comprehensive report embedding images, statistics, and literature references.

**Reason:** Deliver the requested scientific report in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": {},
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

