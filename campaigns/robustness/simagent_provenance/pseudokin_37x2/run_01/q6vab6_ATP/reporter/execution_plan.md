# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requested a comprehensive single‑simulation HTML report that includes embedded plots, key statistics, and literature context. The workflow therefore requires parsing the pre‑generated analysis_summary.jsonl file, generating focused PubMed queries based on the analysis types performed, retrieving relevant literature, and then feeding all of this into the generate_html_report tool. No other tools are needed for this single‑simulation workflow.

## Overview

1️⃣ Read and parse the analysis summary. 2️⃣ Build PubMed queries that target the protein’s functional context, the MD simulation methodology, and the specific analyses performed. 3️⃣ Search PubMed to collect a concise set of recent references. 4️⃣ Create the final HTML report using the parsed data and literature references.

## Report Focus

- Ligand‑pocket dynamics across 37 pseudokinase-ATP holo structures
- Consensus DCCM and RMSF patterns revealing inter‑domain communication
- Key literature that frames MD simulation of pseudokinase ligand interactions

## Execution Steps (5 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the per‑system analysis results, statistics, and image paths from analysis/analysis_summary.jsonl.

**Reason:** We need the analysis data to populate the report and to know which analyses were performed.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create a prioritized list of PubMed queries that combine the protein context, MD simulation, and the specific analyses performed.

**Reason:** Structured queries enable targeted literature retrieval relevant to both the protein and the analytical techniques.

**Parameters:**
```json
{
  "analysis_types": [
    "ligand-pocket distance",
    "consensus DCCM",
    "consensus RMSF",
    "consensus torsions",
    "dihedral PCA",
    "protein RMSF"
  ],
  "user_goal": "Run the full set of per\u2011system analyses on 37 pseudokinase-ATP holo structures and compile a comprehensive report.",
  "protein_name": "pseudokinase",
  "analysis_stats": null
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Query PubMed using the top three queries from the previous step to retrieve recent, high‑impact papers.

**Reason:** Gather up-to-date literature that contextualizes the simulation results.

**Parameters:**
```json
{
  "query": "pseudokinase AND ATP binding AND MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Search PubMed (Secondary Query)

**Tool:** `search_pubmed`

**Description:** Retrieve literature specifically addressing ligand‑pocket dynamics and DCCM analysis in kinase systems.

**Reason:** Provide technical background on the key analyses used.

**Parameters:**
```json
{
  "query": "kinase AND ligand pocket distance AND DCCM AND MD",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 5: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a single‑simulation HTML report that embeds all analysis images, displays key statistics, and includes the literature references collected.

**Reason:** The final deliverable must be an HTML file with embedded visuals and a concise narrative.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

