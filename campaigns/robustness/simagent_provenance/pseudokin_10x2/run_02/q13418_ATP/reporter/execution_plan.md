# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The reporter must produce a concise yet comprehensive HTML report for a single simulation.  The analysis results are already stored in `analysis/analysis_summary.jsonl`.  To provide meaningful context, we will automatically generate PubMed queries based on the types of metrics computed (e.g., ligand‐pocket distance, RMSF, dihedral PCA) and fetch the top references.  These references will be embedded in the report as literature citations.  The workflow uses only the tools that the system offers: `read_analysis_summary`, `search_pubmed`, and `generate_html_report`.

## Overview

1️⃣ Read the analysis summary file to extract all metrics, statistics, and image paths. 2️⃣ Generate a set of PubMed queries that target the protein name (q13418), the simulation approach (MD of a pseudokinase ATP complex), and the specific analysis methods performed. 3️⃣ Execute those queries to collect up to 5 highly relevant abstracts. 4️⃣ Feed the parsed analysis data and literature citations into `generate_html_report`, producing a self‑contained `report.html` in the reporter directory.

## Report Focus

- Ligand pocket distance dynamics and orientation
- Consensus RMSF and protein flexibility
- Dihedral PCA of shared reference torsions
- Consensus DCCM between N‑ and C‑lobes
- Literature comparison of ATP binding in pseudokinases

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse `analysis/analysis_summary.jsonl` to obtain metric tables, statistic summaries, and the file paths of all generated plots.

**Reason:** We need the raw data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create prioritized PubMed search queries that focus on the protein, MD simulation, and the specific analytical methods used.

**Reason:** Targeted queries increase the chance of retrieving high‑quality, relevant literature.

**Parameters:**
```json
{
  "analysis_types": [
    "ligand pocket distance",
    "RMSF",
    "dihedral PCA",
    "DCCM",
    "torsion analysis"
  ],
  "user_goal": "Perform detailed analysis on the two existing 200\u2011ns trajectories (rep01, rep02) of q13418_ATP.",
  "protein_name": "q13418",
  "analysis_stats": {}
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute each generated query and retrieve up to five relevant abstracts for each.

**Reason:** Collect literature that contextualizes our findings.

**Parameters:**
```json
{
  "query": "${generated_query}",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a modern, self‑contained HTML report that embeds all analysis plots, presents key statistics as cards, and cites the retrieved literature.

**Reason:** Deliver the final, publication‑ready artifact.

**Parameters:**
```json
{
  "analysis_data": "${parsed_analysis_summary}",
  "literature_refs": "${merged_pubmed_results}",
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

