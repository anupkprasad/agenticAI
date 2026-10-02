# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a per‑simulation HTML report that pulls all analysis metrics, statistics, and images from the pre‑generated `analysis_summary.jsonl`.  The report must be fully self‑contained, embedding plots as base64 images and highlighting key numerical descriptors.  To meet the specification we simply read the summary file and feed the parsed data into the `generate_html_report` tool.  The tool automatically extracts image paths from the summary, so we need not supply them explicitly.  Optionally, we generate PubMed queries that focus on ATP‑binding pseudokinases and the analysis methods used, allowing a literature context section to be added to the report.

We avoid any analysis or simulation steps, and we do not use the combined‑report generator because this workflow handles a single system only.

## Overview

Generate a comprehensive HTML report for one ATP‑bound pseudokinase system by:
1. Loading analysis results from `analysis/analysis_summary.jsonl`.
2. Optionally creating PubMed search queries to retrieve relevant literature.
3. Invoking `generate_html_report` to produce `report.html` with embedded plots, statistics cards, and a literature context section.
The report will be placed in the reporter’s working directory, ready for inspection or downstream use.

## Report Focus

- Key ATP‑binding pocket metrics (COM distance, orientation, χ1 angles)
- Global protein dynamics (RMSF, DCCM, dihedral PCA entropy)
- Literature context for ATP‑binding pseudokinases and MD analysis methods

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the analysis_summary.jsonl file to obtain all metrics, statistics, and image file paths for the current system.

**Reason:** Need to load the full set of analysis data that will feed the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate PubMed Queries (optional)

**Tool:** `generate_literature_queries`

**Description:** Create search queries that focus on ATP‑binding pseudokinases and the specific analysis techniques performed.

**Reason:** To provide a literature context section in the final report.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "Dihedral PCA",
    "Ligand\u2011pocket distance"
  ],
  "user_goal": "Generate a concise HTML report summarizing the analyses for a single ATP\u2011bound pseudokinase system.",
  "protein_name": "pseudokinase",
  "analysis_stats": {}
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that embeds all plots, presents key statistics, and includes literature references.

**Reason:** Produce the final deliverable that satisfies the user’s reporting requirements.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "enriched_prompt": "Generate a concise HTML report summarizing the analyses for a single ATP\u2011bound pseudokinase system."
}
```

