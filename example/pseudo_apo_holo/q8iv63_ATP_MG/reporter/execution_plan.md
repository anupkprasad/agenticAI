# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

To produce a self‑contained, professional HTML report for a single MD simulation, we must (1) load the analysis results, (2) optionally gather literature context for the target proteins, and (3) generate the report that embeds all visualisations and key statistics. The plan follows the tool constraints: only `read_analysis_summary` and `generate_html_report` are used for the per‑simulation report, while literature queries are produced via `generate_literature_queries` for the user’s optional enrichment.

## Overview

1. Parse the JSONL analysis file to obtain statistics and image paths. 2. Build PubMed search queries for ERBB3, VRK3, MLKL, and TITIN using the analysis types and user goal. 3. Feed the parsed data and literature query list to `generate_html_report`, which will embed all images, create statistic cards, and insert a collapsible literature section.

## Report Focus

- Backbone dynamics (RMSD, radius of gyration)
- Loop flexibility (per‑residue RMSF, especially residues 150–200)
- ATP‑binding site stability (COM distance, DSSP changes)
- Allosteric communication (cross‑correlation maps)
- Literature context for ERBB3, VRK3, MLKL, and TITIN

## Execution Steps (6 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the analysis results, statistics, and file paths from `analysis/analysis_summary.jsonl`.

**Reason:** We need all quantitative results and image locations to populate the report.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries for ERBB3

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that target ERBB3, ATP binding, and MD‑simulation analyses.

**Reason:** We need targeted literature search queries for ERBB3.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DSSP"
  ],
  "user_goal": "Analyze the existing 1\u2011ns MD trajectories for the eight systems (p21860, q8iv63, q8nb16, q8wz42 in both apo and holo forms) that were generated with AMBER99SB\u2011ILDN, TIP3P, 310\u202fK, 1\u202fbar, and 0.15\u202fM NaCl.  For each trajectory compute backbone RMSD, per\u2011residue RMSF (including a bar plot for residues 150\u2013200 where present), radius of gyration, COM distance between ATP and the catalytic pocket (holo only), C\u03b1 dynamic cross\u2011correlation maps, and DSSP evolution for the whole protein and the 150\u2013200 region.  Generate comparative overlay plots and statistical tables across all eight systems.  In the reporter, retrieve literature on ATP binding, activation\u2011loop conformations, and allosteric regulation for ERBB3, VRK3, MLKL, and TITIN, and correlate these findings with the simulation results.",
  "protein_name": "ERBB3"
}
```

### Step 3: Generate Literature Queries for VRK3

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that target VRK3, ATP binding, and MD‑simulation analyses.

**Reason:** We need targeted literature search queries for VRK3.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DSSP"
  ],
  "user_goal": "Analyze the existing 1\u2011ns MD trajectories for the eight systems (p21860, q8iv63, q8nb16, q8wz42 in both apo and holo forms) that were generated with AMBER99SB\u2011ILDN, TIP3P, 310\u202fK, 1\u202fbar, and 0.15\u202fM NaCl.  For each trajectory compute backbone RMSD, per\u2011residue RMSF (including a bar plot for residues 150\u2013200 where present), radius of gyration, COM distance between ATP and the catalytic pocket (holo only), C\u03b1 dynamic cross\u2011correlation maps, and DSSP evolution for the whole protein and the 150\u2013200 region.  Generate comparative overlay plots and statistical tables across all eight systems.  In the reporter, retrieve literature on ATP binding, activation\u2011loop conformations, and allosteric regulation for ERBB3, VRK3, MLKL, and TITIN, and correlate these findings with the simulation results.",
  "protein_name": "VRK3"
}
```

### Step 4: Generate Literature Queries for MLKL

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that target MLKL, ATP binding, and MD‑simulation analyses.

**Reason:** We need targeted literature search queries for MLKL.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DSSP"
  ],
  "user_goal": "Analyze the existing 1\u2011ns MD trajectories for the eight systems (p21860, q8iv63, q8nb16, q8wz42 in both apo and holo forms) that were generated with AMBER99SB\u2011ILDN, TIP3P, 310\u202fK, 1\u202fbar, and 0.15\u202fM NaCl.  For each trajectory compute backbone RMSD, per\u2011residue RMSF (including a bar plot for residues 150\u2013200 where present), radius of gyration, COM distance between ATP and the catalytic pocket (holo only), C\u03b1 dynamic cross\u2011correlation maps, and DSSP evolution for the whole protein and the 150\u2013200 region.  Generate comparative overlay plots and statistical tables across all eight systems.  In the reporter, retrieve literature on ATP binding, activation\u2011loop conformations, and allosteric regulation for ERBB3, VRK3, MLKL, and TITIN, and correlate these findings with the simulation results.",
  "protein_name": "MLKL"
}
```

### Step 5: Generate Literature Queries for TITIN

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that target TITIN, ATP binding, and MD‑simulation analyses.

**Reason:** We need targeted literature search queries for TITIN.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSD",
    "RMSF",
    "DSSP"
  ],
  "user_goal": "Analyze the existing 1\u2011ns MD trajectories for the eight systems (p21860, q8iv63, q8nb16, q8wz42 in both apo and holo forms) that were generated with AMBER99SB\u2011ILDN, TIP3P, 310\u202fK, 1\u202fbar, and 0.15\u202fM NaCl.  For each trajectory compute backbone RMSD, per\u2011residue RMSF (including a bar plot for residues 150\u2013200 where present), radius of gyration, COM distance between ATP and the catalytic pocket (holo only), C\u03b1 dynamic cross\u2011correlation maps, and DSSP evolution for the whole protein and the 150\u2013200 region.  Generate comparative overlay plots and statistical tables across all eight systems.  In the reporter, retrieve literature on ATP binding, activation\u2011loop conformations, and allosteric regulation for ERBB3, VRK3, MLKL, and TITIN, and correlate these findings with the simulation results.",
  "protein_name": "TITIN"
}
```

### Step 6: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create a comprehensive, self‑contained HTML report embedding all images and key statistics, and include a collapsible section summarising the generated literature queries.

**Reason:** This is the final deliverable that the user will review.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html"
}
```

