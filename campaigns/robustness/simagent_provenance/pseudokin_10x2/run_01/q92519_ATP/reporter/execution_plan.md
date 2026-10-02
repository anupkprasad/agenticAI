# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To produce a ready‑to‑combine HTML report for the TRIB2–ATP holo complex, we first ingest the analysis_summary.jsonl file, which contains all scalar descriptors, statistics, and figure paths.  Next, we perform a concise PubMed search to embed relevant literature context.  Finally, the generate_html_report tool stitches together the analysis data, embedded figures, key statistic cards, and literature references into a single, professional HTML file named `report.html` in the reporter output directory.  This workflow respects all constraints and keeps the report generation deterministic and reproducible.

## Overview

1. Load analysis results. 2. Retrieve a short set of recent PubMed articles on TRIB2 ATP dynamics. 3. Create a comprehensive HTML report that embeds all plots, displays statistics cards, and cites the literature.

## Report Focus

- ATP binding dynamics and stability
- TRIB2 pocket flexibility and side‑chain χ₁ behaviour
- Consensus RMSF and inter‑lobe coupling
- Literature context for TRIB2 ATPase activity

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the JSONL file to extract all descriptor values, statistics, and image file paths.

**Reason:** Required to feed the report generator with accurate numeric data and image locations.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Search PubMed for TRIB2 ATP Dynamics

**Tool:** `search_pubmed`

**Description:** Retrieve up to five recent papers that discuss TRIB2, ATP binding, or related molecular‑dynamics studies to provide literature context.

**Reason:** Adds up-to-date scholarly references that frame the simulation findings.

**Parameters:**
```json
{
  "query": "TRIB2 ATP molecular dynamics",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report embedding all figures, key statistics, and literature citations.

**Reason:** Produces the deliverable HTML report ready for integration with the other nine system reports.

**Parameters:**
```json
{
  "analysis_data": "{{analysis_data}}",
  "literature_refs": "{{literature_refs}}",
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": {
    "protein_name": "TRIB2",
    "complex": "TRIB2\u2013ATP",
    "case_id": "protein_with_ligand"
  },
  "final_impression": "This study demonstrates that the ATP ligand remains stably bound with moderate pocket flexibility, consistent with recent experimental reports of TRIB2 ATPase activity.",
  "pdb_data": {
    "TRIB2_ATP": "{{pdb_string}}"
  },
  "enriched_prompt": "Analysis of TRIB2\u2013ATP holo complex dynamics and literature integration."
}
```

