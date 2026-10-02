# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To produce a comprehensive per‑simulation HTML report, we first need to ingest the analysis results stored in `analysis/analysis_summary.jsonl`. These results contain all required statistics and image paths, enabling the report generation tool to embed the visualisations automatically.  Next, we generate context‑relevant literature queries using the analysis types identified in the summary, then query PubMed for recent, high‑impact papers that discuss ATP‑binding dynamics in pseudokinases and the specific metrics analysed (e.g., RMSF, DCCM, dihedral‑PCA).  Finally, the `generate_html_report` tool is invoked with the parsed analysis data and the retrieved literature references, producing a professionally styled HTML report in the reporter directory.  This workflow satisfies the user goal of summarising the ten scalar descriptors, visualising the dynamics, and providing literature context without re‑running any simulation steps.

## Overview

1️⃣ Read `analysis_summary.jsonl`  
2️⃣ Generate PubMed query strings from analysis types  
3️⃣ Search PubMed for relevant literature  
4️⃣ Generate a concise HTML report with embedded plots and literature citations

## Report Focus

- ATP COM distance dynamics
- ATP orientation variability
- Pocket χ1 torsion flexibility
- Consensus‑mapped Cα RMSF
- N‑lobe ↔ C‑lobe DCCM
- Shared‑reference dihedral‑PCA

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file that contains all scalar descriptor statistics and image paths.

**Reason:** The report requires the statistical values and figure paths produced by the analysis agent.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Query Strings

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that prioritise the protein name, MD simulation context, and specific analysis methods.

**Reason:** Structured queries improve PubMed hit relevance for the specific descriptors analysed.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "dihedral-PCA",
    "orientation",
    "distance"
  ],
  "user_goal": "Extract the ten scalar dynamics descriptors and summarise ATP binding behaviour",
  "protein_name": "p51841",
  "analysis_stats": {
    "RMSF": {
      "mean": 1.2,
      "max": 3.8
    },
    "DCCM": {
      "mean": 0.65
    }
  }
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Query PubMed for recent literature that discusses ATP‑binding dynamics in pseudokinases and the analysis methods used.

**Reason:** To provide up‑to‑date scientific context and citations for the report.

**Parameters:**
```json
{
  "query": "p51841 ATP pseudokinase MD simulation",
  "max_results": 10,
  "include_abstracts": true,
  "max_age_years": 5
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report with embedded plots, key statistics, and literature references.

**Reason:** This is the final deliverable requested by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

