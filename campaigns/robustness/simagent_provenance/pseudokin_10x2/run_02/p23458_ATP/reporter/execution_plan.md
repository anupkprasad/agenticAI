# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requires a comprehensive per‑simulation HTML report that summarizes the full 200‑ns MD analyses, highlights key scalar descriptors, and places the findings in a broader literature context. To meet this, we first parse the analysis summary, generate focused PubMed/BioRxiv queries, retrieve relevant literature, and finally invoke `generate_html_report` to embed the analysis visuals and literature citations into a polished web page.

## Overview

1️⃣ Load analysis results from `analysis_summary.jsonl`. 2️⃣ Create PubMed/BioRxiv search queries tailored to the protein‑ATP dynamics and the specific descriptors computed. 3️⃣ Query the literature databases. 4️⃣ Compile all information and generate a self‑contained `report.html` that will be stored in the reporter sub‑directory.

## Report Focus

- ATP pocket mean COM distance and variability across the 200‑ns simulation
- Orientation of ATP relative to the consensus pocket axis
- Consensus pocket side‑chain χ1 torsion distribution
- RMSF and DCCM patterns revealing N‑ vs C‑lobe coupling
- Shared‑reference dihedral PCA revealing collective motions

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file containing the per‑system analysis statistics and figure paths.

**Reason:** We need the numerical metrics and figure locations to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Construct PubMed and BioRxiv search strings that focus on the protein (e.g., the specific pseudokinase accession), the ATP binding pocket, and the analysis methods (RMSF, DCCM, PCA, etc.).

**Reason:** Targeted queries will surface the most relevant mechanistic and methodological studies.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA",
    "ATP binding"
  ],
  "user_goal": "Investigate the comparative dynamics of the ATP pocket across a set of pseudokinase holo complexes and contextualize the observed flexibility in the literature.",
  "protein_name": "p23458",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Retrieve recent peer‑reviewed articles matching the generated queries.

**Reason:** PubMed provides a curated set of journal articles that often include experimental and computational analyses of kinase dynamics.

**Parameters:**
```json
{
  "query": "{{queries.pubmed}}",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Search BioRxiv

**Tool:** `search_biorxiv`

**Description:** Fetch preprints that may discuss cutting‑edge MD simulations of pseudokinases or ATP binding pockets.

**Reason:** Preprints can provide very recent insights not yet indexed by PubMed.

**Parameters:**
```json
{
  "query": "{{queries.biorxiv}}",
  "max_results": 5,
  "max_age_years": 5
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a polished HTML page embedding the analysis images, statistics cards, and literature citations.

**Reason:** This is the final deliverable that will be placed in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_data}}",
  "literature_refs": [
    "{{pubmed_results}}",
    "{{biorxiv_results}}"
  ],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": {
    "protein": "p23458",
    "ligand": "ATP",
    "trajectory_length_ns": 200
  }
}
```

