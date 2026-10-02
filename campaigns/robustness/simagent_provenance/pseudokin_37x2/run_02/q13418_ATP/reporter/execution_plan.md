# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a single‑simulation scientific report that summarizes the ten averaged scalar descriptors computed for each of the 37 holo‑ATP PDBs.  The analysis results are already stored in `/analysis/analysis_summary.jsonl`.  We only need to parse this file, then feed the parsed data to the `generate_html_report` tool, which will automatically embed any image paths it finds, create statistics cards, and produce a modern, professional HTML document named `report.html`.  No additional preprocessing or new simulation is required.  Literature search is optional, so it is omitted to keep the workflow simple and focused on the required deliverable.

## Overview

1️⃣ Read the analysis summary JSONL file.  2️⃣ Pass the parsed data to the HTML‑report generator to produce a single, comprehensive report (`report.html`) that embeds all visualizations and highlights key statistics for each descriptor.

## Report Focus

- Average ATP‑COM distance and its dispersion
- Orientation axis angle stability
- Side‑chain χ1 packing in the ATP pocket
- Consensus Cα RMSF across the protein
- Inter‑lobe dynamic coupling (DCCM)
- Entropy of dihedral PCA modes

## Execution Steps (2 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load and parse the pre‑generated `analysis_summary.jsonl` file to obtain all scalar descriptors, their means, SDs, and any image file references.

**Reason:** We need the analysis data to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report that includes embedded images, statistics cards, and a modern layout.

**Reason:** This tool produces the final deliverable – the per‑simulation report required by the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": null,
  "final_impression": null,
  "pdb_data": null,
  "enriched_prompt": null
}
```

