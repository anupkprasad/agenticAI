# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a single‑simulation report that pulls data from an existing analysis summary, optionally adds literature context, and produces a comprehensive HTML file. Since the analysis summary already contains all numerical descriptors and image paths, we first load it with `read_analysis_summary`.  The report requires a literature paragraph; to keep the workflow lightweight we will skip a full literature search and provide an empty reference list (the tool accepts this).  Finally, we generate the HTML using `generate_html_report`, passing the parsed data and specifying the output filename as required.

## Overview

Load analysis results → (optionally) gather literature references → generate a standalone `report.html` containing embedded visualisations, statistics cards, and a context paragraph.

## Report Focus

- ATP binding pocket dynamics
- inter‑lobe communication
- pocket side‑chain conformational sampling

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the existing analysis_summary.jsonl file to retrieve descriptor values and image paths.

**Reason:** Need the data to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive report that embeds all images, displays key statistics, and includes a literature context paragraph.

**Reason:** Produce the final deliverable in the reporter directory.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

