# Analysis Summary File Guide

## Overview

The analysis summary file (`analysis_summary.jsonl`) provides a centralized, machine-readable log of all MD analysis results. This file is automatically created and updated during analysis workflows.

## Key Features

- **Automatic Creation**: Initialized at the start of analysis workflow
- **Easy to Parse**: JSON Lines format (one JSON object per line)
- **Agent-Friendly**: Structured data that can be easily read by LLM agents
- **Human-Readable**: Can be inspected directly or via utility functions
- **Comprehensive**: Captures statistics, file paths, and metadata from all analyses

## File Format

**Location**: `working_dir/analysis/analysis_summary.jsonl`

**Format**: JSON Lines (.jsonl) - each line is a complete JSON object

### First Line (Header)
```json
{
  "summary_file_version": "1.0",
  "created_at": "2026-03-03T15:00:00Z",
  "description": "MD Analysis Summary - One JSON object per line",
  "format": "JSON Lines (.jsonl)"
}
```

### Subsequent Lines (Analysis Entries)
```json
{
  "timestamp": "2026-03-03T15:30:00Z",
  "analysis_type": "RMSF",
  "statistics": {
    "n_residues": 255,
    "mean_rmsf_angstrom": 12.77,
    "std_rmsf_angstrom": 3.63,
    "min_rmsf_angstrom": 6.49,
    "max_rmsf_angstrom": 20.46,
    "most_flexible_residue": 221,
    "most_flexible_rmsf": 20.46
  },
  "files": {
    "topology": "working_dir/hpc/md.gro",
    "trajectory": "working_dir/hpc/md.xtc",
    "output": "rmsf.dat"
  },
  "metadata": {
    "selection": "protein and name CA",
    "top_5_flexible": [...],
    "top_5_rigid": [...]
  }
}
```

## Analysis Types

### 1. RMSF (Root Mean Square Fluctuation)
```json
{
  "analysis_type": "RMSF",
  "statistics": {
    "n_residues": int,
    "mean_rmsf_angstrom": float,
    "std_rmsf_angstrom": float,
    "min_rmsf_angstrom": float,
    "max_rmsf_angstrom": float,
    "most_flexible_residue": int,
    "most_flexible_rmsf": float
  },
  "metadata": {
    "selection": "protein and name CA",
    "top_5_flexible": [{"residue_id": int, "residue_name": str, "rmsf": float}],
    "top_5_rigid": [...]
  }
}
```

**Output File Format Change**: Now outputs only `residue_id` and `rmsf_value`:
```
# Residue_ID    RMSF(Angstrom)
1              9.8281
2              9.8726
3              8.9809
```

### 2. RMSD (Root Mean Square Deviation)
```json
{
  "analysis_type": "RMSD",
  "statistics": {
    "n_frames": int,
    "mean_rmsd_angstrom": float,
    "std_rmsd_angstrom": float,
    "min_rmsd_angstrom": float,
    "max_rmsd_angstrom": float
  },
  "metadata": {
    "selection": "protein and name CA",
    "reference_frame": 0
  }
}
```

### 3. Radius of Gyration
```json
{
  "analysis_type": "Radius_of_Gyration",
  "statistics": {
    "n_frames": int,
    "mean_rg_angstrom": float,
    "std_rg_angstrom": float,
    "min_rg_angstrom": float,
    "max_rg_angstrom": float
  },
  "metadata": {
    "selection": "protein"
  }
}
```

### 4. Energy Analysis
```json
{
  "analysis_type": "Energy",
  "statistics": {
    "n_frames": int,
    "Potential_mean": float,
    "Potential_std": float,
    "Kinetic-En._mean": float,
    "Kinetic-En._std": float,
    "Temperature_mean": float,
    "Temperature_std": float
  },
  "metadata": {
    "terms_analyzed": ["Potential", "Kinetic-En.", "Temperature"],
    "detailed_statistics": {...}
  }
}
```

## Python API

### Read Summary File
```python
from src.analysis.summary_logger import read_summary_file

# Read all entries
entries = read_summary_file("working_dir/analysis")

# Skip header (first line)
analysis_entries = [e for e in entries if "analysis_type" in e]

# Print each analysis
for entry in analysis_entries:
    print(f"{entry['timestamp']}: {entry['analysis_type']}")
    print(f"  Statistics: {entry['statistics']}")
```

### Get Latest Analysis
```python
from src.analysis.summary_logger import get_latest_analysis

# Get most recent analysis of any type
latest = get_latest_analysis("working_dir/analysis")

# Get most recent RMSF analysis
latest_rmsf = get_latest_analysis("working_dir/analysis", analysis_type="RMSF")

print(f"Latest RMSF: mean={latest_rmsf['statistics']['mean_rmsf_angstrom']:.2f} Å")
```

### Generate Human-Readable Report
```python
from src.analysis.summary_logger import generate_summary_report

report = generate_summary_report("working_dir/analysis")
print(report)
```

Output:
```
================================================================================
MD ANALYSIS SUMMARY REPORT
================================================================================

[1] RMSF - 2026-03-03T15:30:00Z
--------------------------------------------------------------------------------
  Statistics:
    • n_residues: 255
    • mean_rmsf_angstrom: 12.7719
    • std_rmsf_angstrom: 3.6277
    • max_rmsf_angstrom: 20.4625
  Files:
    • topology: working_dir/hpc/md.gro
    • trajectory: working_dir/hpc/md.xtc
    • output: rmsf.dat
...
```

## For Agents

Agents can easily parse the summary file to understand what analyses have been performed and access key results without parsing individual data files.

### Example Agent Query
"Read the analysis summary file and tell me which residue is most flexible"

Agent would:
1. Read `working_dir/analysis/analysis_summary.jsonl`
2. Find the RMSF entry
3. Extract `statistics.most_flexible_residue` and `statistics.most_flexible_rmsf`
4. Respond: "Residue 221 is the most flexible with RMSF of 20.46 Å"

## Benefits

1. **Centralized**: All analysis metrics in one location
2. **Structured**: Consistent JSON format across all analysis types
3. **Append-Only**: New analyses are added without modifying existing entries
4. **Machine-Readable**: Easy for agents to parse and extract information
5. **Traceable**: Timestamps and file paths provide full traceability
6. **Extensible**: New analysis types can easily be added

## File Size Considerations

The summary file is lightweight - each entry is typically less than 1KB. Even after hundreds of analyses, the file remains small and fast to parse.

## Integration with Workflow

The summary file is automatically:
- **Initialized**: When `AnalysisToolExecutor` is created
- **Updated**: After each successful analysis (RMSD, RMSF, Rg, Energy)
- **Location**: Always in `working_dir/analysis/analysis_summary.jsonl`

No manual intervention required!
