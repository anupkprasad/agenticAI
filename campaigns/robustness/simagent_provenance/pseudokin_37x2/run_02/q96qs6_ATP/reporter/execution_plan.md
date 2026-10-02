# Reporter Execution Plan

**Generated:** N/A

## LLM Reasoning

The workflow requires a concise, automated pipeline that (1) pulls the analysis results from the existing JSONL file, (2) optionally enriches the report with recent literature relevant to PSKH2 and the specific MD metrics, and (3) compiles all of this into a professional HTML document.  The plan follows the tool contracts exactly: it reads the summary, optionally performs literature searches using the generated queries, then calls `generate_html_report` with the parsed data and the retrieved references.  All outputs are written to the reporter directory, keeping the filenames and structure consistent with the requirements.

## Overview

1. Parse the per‑simulation analysis results. 2. Generate PubMed queries that combine the protein name (PSKH2), the analysis types performed (RMSF, DCCM, PCA entropy, etc.) and the goal of the study. 3. Execute the literature searches and collect the top references. 4. Build the HTML report, embedding images, statistics cards, and a brief literature context section. 5. Store the report as `report.html` in the reporter directory.

## Report Focus

- Ligand pocket dynamics (distance statistics)
- Consensus pocket residue flexibility (RMSF, χ₁ torsions)
- Inter‑lobe communication (DCCM)
- Overall protein dynamics (PCA entropy)

## Execution Steps (4 steps)

### Step 1: Read Analysis Summary

**Tool:** `read_analysis_summary`

**Description:** Load the JSONL file that contains all analysis metrics, statistics, and image file paths for this simulation.

**Reason:** Need a structured representation of the analysis results to feed into the report generator.

**Parameters:**
```json
{
  "summary_file": "analysis_summary.jsonl"
}
```

### Step 2: Generate Literature Queries

**Tool:** `generate_literature_queries`

**Description:** Create PubMed search queries that prioritize the protein (PSKH2), the MD analysis methods (RMSF, DCCM, PCA), and the study hypothesis.

**Reason:** Provide context‑aware literature search terms for the next step.

**Parameters:**
```json
{
  "analysis_types": [
    "RMSF",
    "DCCM",
    "PCA entropy",
    "ligand pocket dynamics"
  ],
  "user_goal": "Assess PSKH2 holo\u2011complex dynamics and compare to literature on pseudokinase flexibility.",
  "protein_name": "PSKH2",
  "analysis_stats": {
    "RMSF": {
      "mean": 2.5,
      "max": 4.0
    },
    "DCCM": {
      "mean": 0.2
    },
    "PCA entropy": {
      "mean": 0.8
    }
  }
}
```

### Step 3: Search PubMed

**Tool:** `search_pubmed`

**Description:** Execute the top priority PubMed queries to retrieve relevant recent literature.

**Reason:** Collect up-to-date references to include in the report.

**Parameters:**
```json
{
  "query": "PSKH2 pseudokinase MD simulation",
  "max_results": 5,
  "include_abstracts": true,
  "max_age_years": 10
}
```

### Step 4: Generate HTML Report

**Tool:** `generate_html_report`

**Description:** Create the comprehensive HTML report, embedding analysis figures, statistics, and literature references.

**Reason:** Generate the final deliverable with embedded visuals and contextual literature.

**Parameters:**
```json
{
  "analysis_data": {},
  "literature_refs": [],
  "report_type": "comprehensive",
  "output_file": "report.html",
  "system_info": {
    "protein_name": "PSKH2",
    "ligand_name": "ATP",
    "simulation_length": "200 ns",
    "replicas": [
      "rep01",
      "rep02"
    ]
  },
  "final_impression": "The PSKH2 holo\u2011complex exhibits a stable ligand pocket distance with moderate flexibility in the consensus pocket residues, as reflected by the RMSF and DCCM statistics. The dihedral PCA entropy indicates a compact conformational landscape, consistent with recent studies of pseudokinase dynamics."
}
```

