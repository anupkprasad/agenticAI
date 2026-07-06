"""
Analysis Summary Logger - Centralized logging for MD analysis results

This module provides a centralized summary file that logs important metrics
from all analysis types. The summary file uses JSON Lines format (one JSON
object per line) for easy parsing by agents and humans.

Summary file structure: analysis_summary.jsonl
Each line is a JSON object with:
- timestamp: ISO timestamp
- analysis_type: Type of analysis (RMSD, RMSF, Rg, energy, etc.)
- statistics: Key statistical measures
- files: Input/output file paths
- metadata: Additional context
"""
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

SUMMARY_FILENAME = "analysis_summary.jsonl"


def _json_default(obj: Any) -> Any:
    """Fallback serializer for numpy/scalar types json.dumps can't handle natively."""
    # numpy scalars expose .item(); arrays expose .tolist()
    item = getattr(obj, "item", None)
    if callable(item):
        try:
            return obj.item()
        except Exception:
            pass
    tolist = getattr(obj, "tolist", None)
    if callable(tolist):
        try:
            return obj.tolist()
        except Exception:
            pass
    return str(obj)


def _dumps(obj: Any, **kwargs: Any) -> str:
    """json.dumps with numpy-aware default so int64/float64/ndarray never crash."""
    kwargs.setdefault("default", _json_default)
    return json.dumps(obj, **kwargs)


def _round_floats(obj: Any, decimals: int = 3) -> Any:
    """
    Recursively round floats and coerce numpy scalars to native Python types.
    
    Args:
        obj: Object to process (dict, list, float, or other)
        decimals: Number of decimal places to round to
        
    Returns:
        Object with floats rounded and numpy scalars converted
    """
    if isinstance(obj, dict):
        return {key: _round_floats(value, decimals) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [_round_floats(item, decimals) for item in obj]
    elif isinstance(obj, tuple):
        return [_round_floats(item, decimals) for item in obj]
    elif isinstance(obj, float):
        return round(obj, decimals)
    elif isinstance(obj, (bool, int, str)) or obj is None:
        return obj
    else:
        # numpy scalar (int64/float64) or ndarray → native Python
        native = _json_default(obj)
        # Re-round if the coerced value is a float / list of floats
        if isinstance(native, (float, list, dict)):
            return _round_floats(native, decimals)
        return native


def initialize_summary_file(working_dir: str) -> str:
    """
    Initialize the analysis summary file.
    Creates the file if it doesn't exist and writes header information.
    
    Args:
        working_dir: Working directory for analysis
        
    Returns:
        Path to the summary file
    """
    summary_path = Path(working_dir) / SUMMARY_FILENAME
    
    # Create working directory if needed
    Path(working_dir).mkdir(parents=True, exist_ok=True)
    
    # If file doesn't exist, create with header
    if not summary_path.exists():
        header = {
            "summary_file_version": "1.0",
            "created_at": datetime.utcnow().isoformat(),
            "description": "MD Analysis Summary - Pretty-printed JSON for readability",
            "format": "Multi-line JSON objects separated by newlines",
            "fields": {
                "timestamp": "ISO timestamp of analysis",
                "analysis_type": "Type of analysis performed",
                "statistics": "Key statistical measures",
                "files": "Input/output file paths",
                "metadata": "Key observations and additional context (selections, parameters, notable residues)"
            }
        }
        
        with open(summary_path, 'w') as f:
            # Write header with indentation for readability
            f.write(_dumps(header, indent=2) + "\n")
        
        logger.info(f"Initialized analysis summary file: {summary_path}")
    
    return str(summary_path)


def append_analysis_summary(
    working_dir: str,
    analysis_type: str,
    statistics: Dict[str, Any],
    files: Optional[Dict[str, str]] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> None:
    """
    Append analysis results to the summary file.
    
    Args:
        working_dir: Working directory for analysis
        analysis_type: Type of analysis (e.g., "RMSD", "RMSF", "Rg", "Energy")
        statistics: Dictionary of statistical measures
        files: Dictionary of input/output file paths
        metadata: Additional metadata (selection, parameters, etc.)
    """
    summary_path = Path(working_dir) / SUMMARY_FILENAME
    
    # Ensure summary file exists
    if not summary_path.exists():
        initialize_summary_file(working_dir)
    
    # Round all float values to 3 decimal places
    statistics = _round_floats(statistics or {}, decimals=3)
    metadata = _round_floats(metadata or {}, decimals=3)
    
    # Ensure Path objects and lists in files dict are JSON-serializable
    safe_files: Dict[str, Any] = {}
    for k, v in (files or {}).items():
        if isinstance(v, (list, tuple)):
            safe_files[k] = [str(item) for item in v]
        else:
            safe_files[k] = str(v)
    
    # Format timestamp in readable format: "2026-03-03, Time 23:56:00"
    now = datetime.utcnow()
    formatted_timestamp = f"{now.strftime('%Y-%m-%d')}, Time {now.strftime('%H:%M:%S')}"
    
    # Create summary entry
    entry = {
        "timestamp": formatted_timestamp,
        "analysis_type": analysis_type,
        "statistics": statistics,
        "files": safe_files,
        "metadata": metadata
    }
    
    # Append to file
    try:
        with open(summary_path, 'a') as f:
            # Write separator for readability
            f.write("---\n")
            # Write pretty-printed JSON with indentation for readability
            f.write(_dumps(entry, indent=2) + "\n")
        
        logger.info(f"Appended {analysis_type} summary to {summary_path}")
    except Exception as e:
        logger.error(f"Failed to write to summary file: {e}")


def append_trajectory_batch_summary(
    working_dir: str,
    session_stats: Dict[str, Any],
    *,
    aligned_metrics: Optional[List[str]] = None,
    raw_streaming_metrics: Optional[List[str]] = None,
    raw_batch_metrics: Optional[List[str]] = None,
    step_indices: Optional[List[int]] = None,
    topology_file: Optional[str] = None,
    trajectory_file: Optional[str] = None,
) -> None:
    """Log trajectory batch orchestration stats to analysis_summary.jsonl."""
    append_analysis_summary(
        working_dir=working_dir,
        analysis_type="TrajectoryBatch",
        statistics={
            "universe_loads": session_stats.get("universe_loads", 0),
            "align_runs": session_stats.get("align_runs", 0),
            "n_passes": len(session_stats.get("passes", []) or []),
            "n_metrics_batched": len(step_indices or []),
        },
        files={
            "topology": topology_file or "",
            "trajectory": trajectory_file or "",
        },
        metadata={
            "session_stats": session_stats,
            "aligned_metrics": aligned_metrics or [],
            "raw_streaming_metrics": raw_streaming_metrics or [],
            "raw_batch_metrics": raw_batch_metrics or [],
            "batched_step_indices": step_indices or [],
        },
    )


def read_summary_file(working_dir: str) -> list:
    """
    Read and parse the analysis summary file.
    
    Handles both old single-line JSONL format and new multi-line JSON format.
    
    Args:
        working_dir: Working directory for analysis
        
    Returns:
        List of summary entries (parsed JSON objects)
    """
    summary_path = Path(working_dir) / SUMMARY_FILENAME
    
    if not summary_path.exists():
        return []
    
    entries = []
    try:
        with open(summary_path, 'r') as f:
            content = f.read()
        
        # Split by separator for multi-line format
        blocks = content.split('---\n')
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            
            try:
                # Try to parse as JSON
                entry = json.loads(block)
                entries.append(entry)
            except json.JSONDecodeError:
                # Might be old single-line format, try line-by-line
                for line in block.split('\n'):
                    line = line.strip()
                    if line:
                        try:
                            entries.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        
        logger.info(f"Read {len(entries)} entries from summary file")
        return entries
    
    except Exception as e:
        logger.error(f"Failed to read summary file: {e}")
        return []


def update_analysis_summary_with_files(
    working_dir: str,
    analysis_type: str,
    additional_files: Dict[str, str]
) -> None:
    """
    Update an existing analysis summary entry by adding plot files or other outputs.
    
    This is useful when plots are generated separately from the calculators.
    Updates the most recent entry of the specified analysis_type.
    
    Args:
        working_dir: Working directory for analysis
        analysis_type: Type of analysis to update (e.g., "RMSD", "RMSF", "Rg")
        additional_files: Dictionary of additional files to add (e.g., {"plot": "rmsd_plot.png"})
    """
    summary_path = Path(working_dir) / SUMMARY_FILENAME
    
    if not summary_path.exists():
        logger.warning(f"Summary file not found: {summary_path}")
        return
    
    try:
        # Read all entries
        entries = read_summary_file(working_dir)
        
        # Find the most recent entry of this analysis type
        # Try exact match first, then case-insensitive substring match
        updated = False
        for entry in reversed(entries):  # Start from most recent
            entry_type = entry.get("analysis_type", "")
            if (entry_type == analysis_type
                    or entry_type.upper() == analysis_type.upper()
                    or analysis_type.upper() in entry_type.upper()):
                # Update the files dict
                if "files" not in entry:
                    entry["files"] = {}
                entry["files"].update(additional_files)
                updated = True
                logger.info(f"Updated {entry_type} entry with files: {list(additional_files.keys())}")
                break
        
        if not updated:
            logger.warning(f"No {analysis_type} entry found to update")
            return
        
        # Rewrite the entire summary file
        with open(summary_path, 'w') as f:
            for entry in entries:
                if entry.get("summary_file_version"):  # Header entry
                    f.write(_dumps(entry, indent=2) + "\n")
                else:
                    f.write("---\n")
                    f.write(_dumps(entry, indent=2) + "\n")
        
        logger.info(f"Successfully updated summary file: {summary_path}")
        
    except Exception as e:
        logger.error(f"Failed to update summary file: {e}")


def infer_analysis_type_from_files(working_dir: str, data_files: List[str]) -> Optional[str]:
    """
    Infer the analysis_type by matching data file paths against existing summary entries.
    
    Searches all summary entries and returns the analysis_type of the entry
    whose 'files' dict contains one of the given data_files (by basename match).
    
    Args:
        working_dir: Working directory containing analysis_summary.jsonl
        data_files: List of data file paths/names used in the plot
        
    Returns:
        Matching analysis_type string, or None if no match
    """
    if not data_files:
        return None
    
    entries = read_summary_file(working_dir)
    if not entries:
        return None
    
    # Normalize input filenames to basenames for comparison
    input_basenames = set()
    for f in data_files:
        if isinstance(f, str) and f:
            input_basenames.add(Path(f).name.lower())
    
    if not input_basenames:
        return None
    
    # Search entries in reverse (most recent first) for a file match
    for entry in reversed(entries):
        entry_files = entry.get("files", {})
        if not isinstance(entry_files, dict):
            continue
        for file_path in entry_files.values():
            if isinstance(file_path, str):
                if Path(file_path).name.lower() in input_basenames:
                    return entry.get("analysis_type")
    
    return None


def get_latest_analysis(working_dir: str, analysis_type: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Get the most recent analysis entry from the summary file.
    
    Args:
        working_dir: Working directory for analysis
        analysis_type: Filter by analysis type (optional)
        
    Returns:
        Latest analysis entry or None
    """
    entries = read_summary_file(working_dir)
    
    # Skip header entry (first line)
    data_entries = [e for e in entries if "analysis_type" in e]
    
    if not data_entries:
        return None
    
    # Filter by type if specified
    if analysis_type:
        data_entries = [e for e in data_entries if e.get("analysis_type") == analysis_type]
    
    if not data_entries:
        return None
    
    # Return most recent
    return data_entries[-1]


def generate_summary_report(working_dir: str) -> str:
    """
    Generate a human-readable summary report from the summary file.
    
    Args:
        working_dir: Working directory for analysis
        
    Returns:
        Formatted summary report string
    """
    entries = read_summary_file(working_dir)
    
    # Skip header
    data_entries = [e for e in entries if "analysis_type" in e]
    
    if not data_entries:
        return "No analysis results found."
    
    report = []
    report.append("=" * 80)
    report.append("MD ANALYSIS SUMMARY REPORT")
    report.append("=" * 80)
    report.append("")
    
    for i, entry in enumerate(data_entries, 1):
        report.append(f"[{i}] {entry['analysis_type']} - {entry['timestamp']}")
        report.append("-" * 80)
        
        # Statistics
        if entry.get("statistics"):
            report.append("  Statistics:")
            for key, value in entry["statistics"].items():
                if isinstance(value, float):
                    report.append(f"    • {key}: {value:.4f}")
                else:
                    report.append(f"    • {key}: {value}")
        
        # Files
        if entry.get("files"):
            report.append("  Files:")
            for key, value in entry["files"].items():
                report.append(f"    • {key}: {value}")
        
        # Metadata
        if entry.get("metadata"):
            report.append("  Metadata:")
            for key, value in entry["metadata"].items():
                if isinstance(value, (list, dict)):
                    report.append(f"    • {key}: {_dumps(value)[:60]}...")
                else:
                    report.append(f"    • {key}: {value}")
        
        report.append("")
    
    return "\n".join(report)
