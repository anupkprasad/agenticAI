# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The user requests a single‑simulation scientific report that incorporates all analysis outputs stored in the `analysis/analysis_summary.jsonl` file.  The workflow therefore requires (1) parsing that JSONL to extract numerical statistics and image file paths, (2) optional literature contextualization, and (3) generating a professional HTML report that embeds the images, presents key statistics, and highlights the major findings for each protein.  The plan below adheres to the tool usage guidelines: it uses only `read_analysis_summary` and `generate_html_report`, supplies the exact filenames expected by the system, and leaves optional literature searching for the user to trigger if desired.

## Overview

Read the analysis summary, build a data dictionary for each protein, optionally formulate PubMed queries, and create a single comprehensive HTML report (`report.html`) with embedded visuals and statistics.

## Report Focus

- Comparison of apo vs holo dynamics across ERBB3, VRK3, MLKL, and TITIN
- Identification of activation‑loop conformational changes and allosteric signatures

## Execution Steps (3 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Parse the `analysis/analysis_summary.jsonl` file to extract all analysis results, including statistical metrics (means, stds, min, max) and file paths for the generated plots.

**Reason:** Load the complete analysis dataset for further processing.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Search Queries (optional)

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that prioritize the protein name and the specific MD analysis methods performed.  These queries are provided for the user to run via `search_pubmed` if desired.

**Reason:** Provide user with ready‑to‑run PubMed queries for context.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "Radius of Gyration",
    "Cross\u2011Correlation",
    "DSSP"
  ],
  "user_goal": "Analyze the eight pre\u2011existing 1\u2011ns trajectories (four apo and four holo for ERBB3, VRK3, MLKL, and TITIN) using the default AMBER99SB\u2011ILDN/TIP3P 310\u202fK/1\u202fbar 0.15\u202fM NaCl conditions. For each system compute: (1) backbone RMSD; (2) per\u2011residue RMSF with a bar plot for residues 150\u2013200 where present; (3) radius of gyration; (4) COM distance between ATP and the catalytic pocket for the holo runs; (5) C\u03b1 dynamic cross\u2011correlation matrices and apo\u2011vs\u2011holo difference maps; (6) DSSP secondary\u2011structure evolution for the entire protein and residues 150\u2013200. Generate overlay plots and statistical tables comparing apo versus holo across all four proteins. Finally, compile a report that retrieves literature on activation\u2011loop conformations, allosteric regulation, and MD/experimental dynamics for each protein, and correlates these findings with the simulation results.",
  "protein_name": "",
  "analysis_stats": {}
}
```

### Step 3: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive HTML report (`report.html`) that embeds all analysis images, displays key statistics as cards, and structures the content into clear sections for each analysis type.  The report will also include a collapsible panel for literature references if the user decides to supply them.

**Reason:** Produce the final deliverable for the user.

**Parameters:**
```json
{
  "analysis_data": {},
  "output_file": "report.html",
  "report_type": "comprehensive"
}
```

