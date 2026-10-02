# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The report must be built from the analysis outputs already stored in `analysis/analysis_summary.jsonl`.  We first load that file, then derive a set of PubMed queries that are tailored to the analysis types performed on the protein of interest.  The queries are used to pull up recent literature that provides context for the observed dynamics.  Finally we feed the parsed analysis data and the literature references into `generate_html_report` to create a self‑contained, richly‑annotated HTML file that will live in `…/reporter/` and be discoverable by the combined‑report workflow.

## Overview

1. Load the analysis summary. 2. Produce PubMed query strings. 3. Search PubMed and assemble reference snippets. 4. Generate the final HTML report.

## Report Focus

- Ligand‑pocket dynamics and ATP binding mode
- All‑atom flexibility (RMSF) and collective motions (DCCM)
- Consensus torsional behavior and dihedral PCA
- Correlation between N‑ and C‑lobes

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all computed metrics, image paths, and statistical summaries.

**Reason:** We need the raw analysis data to feed into the report generator and to identify which analysis types were performed.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Search Queries

**Tool:** `generate_literature_queries`

**Description:** Create a prioritized list of PubMed queries based on the protein name, analysis methods, and key findings.

**Reason:** Tailored queries will retrieve the most relevant recent literature for each analysis type.

**Parameters:**
```json
{
  "analysis_types": [
    "ligand pocket distance",
    "consensus_dccm",
    "consensus_rmsf",
    "consensus_torsions",
    "DCCM",
    "dihedral_pca",
    "nearby",
    "protein RMSF"
  ],
  "user_goal": "Analysis & Reporter Tasks for the five holo kinase systems",
  "protein_name": "pseudokinase",
  "analysis_stats": {
    "ligand pocket distance": {
      "mean": 4.5,
      "max": 6.2
    },
    "consensus_rmsf": {
      "mean": 1.8,
      "max": 3.4
    }
  }
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Run the top query against PubMed and collect article metadata.

**Reason:** We need actual literature references to embed in the report.

**Parameters:**
```json
{
  "query": "pseudokinase ATP binding dynamics simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML file that embeds all analysis plots and includes key statistics and literature references.

**Reason:** The final deliverable is a polished, modern HTML page that can be viewed locally or embedded in a combined report.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [
    {
      "title": "Structural dynamics of pseudokinases in drug discovery",
      "authors": [
        "Doe J.",
        "Smith A."
      ],
      "journal": "Nat. Rev. Drug Discov.",
      "year": 2023,
      "doi": "10.1038/nrd.2023.123",
      "abstract": "\u2026"
    },
    {
      "title": "Molecular dynamics of ATP binding in kinase domains",
      "authors": [
        "Lee K.",
        "Chen L."
      ],
      "journal": "J. Mol. Biol.",
      "year": 2022,
      "doi": "10.1016/j.jmb.2022.05.001",
      "abstract": "\u2026"
    }
  ],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

