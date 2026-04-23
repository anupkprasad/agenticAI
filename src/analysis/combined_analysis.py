"""
Combined Analysis Tools - Cross-simulation comparison utilities

Provides tools to collect metric data from multiple simulation directories,
produce overlay plots, and compute summary statistics tables.  Designed
for the "combined_analysis" phase of multi-simulation workflows.

Each function follows the same @tool convention used by the other modules
in src/analysis/ (returns a Dict[str, Any] with at least a "success" key).
"""
import os
import csv
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from langchain.tools import tool

logger = logging.getLogger(__name__)

# Optional heavy deps
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib not available — overlay plots will be skipped")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_metric_file(directory: str, filename_pattern: str) -> Optional[str]:
    """
    Search *directory* recursively for the first file whose stem starts with
    *filename_pattern* (case-insensitive).

    Using a stem-prefix match (``stem.startswith``) instead of a substring
    match prevents false hits where a pattern is embedded inside a longer
    filename.  For example, ``"rg"`` must NOT match ``energy_output.xvg``
    even though the substring "rg" appears inside "ene**rg**y".

    Returns the full path or None.
    """
    d = Path(directory)
    if not d.is_dir():
        return None
    pat = filename_pattern.lower()
    for p in sorted(d.rglob("*")):
        if p.is_file() and p.stem.lower().startswith(pat):
            return str(p)
    return None


def _read_two_column_file(
    filepath: str,
    y_col: int = 1,
) -> Tuple[List[float], List[float]]:
    """
    Read a whitespace-or-comma-separated data file.

    Lines starting with '#' or '@' are treated as comments / metadata.
    Returns (x_values, y_values) as lists of floats.

    Time-unit auto-conversion
    -------------------------
    If the comment header (lines starting with ``#``) mentions ``"(ps)"``
    or ``"label \"Time (ps)\""`` (GROMACS xvg style), the first column
    is divided by 1000 to convert ps → ns so all combined plots share the
    same x-axis unit.

    y_col: index of the column to use as y (default 1 = second column).
           Energy xvg files have columns [time, Potential, Kinetic, Temp];
           use y_col=1 to get Potential.

    Raises ValueError when the file cannot be parsed.
    """
    xs, ys = [], []
    convert_x_to_ns = False  # will be set True when header says ps

    with open(filepath, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            raw = line.strip()
            if not raw:
                continue

            # ── Header / metadata lines ───────────────────────────────
            if raw.startswith("#") or raw.startswith("@"):
                low = raw.lower()
                # Detect ps time axis from comment or xvg @xaxis label
                if "(ps)" in low or 'label "time (ps)"' in low or "time(ps)" in low:
                    convert_x_to_ns = True
                continue

            # ── Data lines ────────────────────────────────────────────
            parts = raw.replace(",", " ").split()
            if len(parts) >= y_col + 1:
                try:
                    xs.append(float(parts[0]))
                    ys.append(float(parts[y_col]))
                except ValueError:
                    continue

    if not xs:
        raise ValueError(f"No numeric data found in {filepath}")

    if convert_x_to_ns:
        xs = [x / 1000.0 for x in xs]

    return xs, ys


def _float_stats(values: List[float]) -> Dict[str, float]:
    """Return mean/std/min/max rounded to 3 d.p."""
    if not values:
        return {}
    if HAS_NUMPY:
        arr = np.array(values)
        return {
            "mean": round(float(arr.mean()), 3),
            "std":  round(float(arr.std()),  3),
            "min":  round(float(arr.min()),  3),
            "max":  round(float(arr.max()),  3),
        }
    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n
    return {
        "mean": round(mean, 3),
        "std":  round(variance ** 0.5, 3),
        "min":  round(min(values), 3),
        "max":  round(max(values), 3),
    }


# ---------------------------------------------------------------------------
# Public @tool functions
# ---------------------------------------------------------------------------

@tool
def collect_metric_files(
    sim_dirs: List[str],
    metric_filename: str,
    search_subdir: str = "analysis",
) -> Dict[str, Any]:
    """
    Find a metric data file in each simulation directory.

    Searches ``{sim_dir}/{search_subdir}/`` (and all sub-folders) for the
    first file whose name contains *metric_filename* (e.g. ``"rmsd.dat"``).

    Args:
        sim_dirs: List of per-simulation working directories to search.
        metric_filename: Filename pattern to look for, e.g. ``"rmsd.dat"``.
        search_subdir: Sub-directory name to search inside each sim_dir
            (default: ``"analysis"``).

    Returns:
        Dict with keys:

        * ``found`` – list of ``{"sim_dir": ..., "file": ...}`` dicts
        * ``missing`` – list of sim_dirs where the file was not found
        * ``success`` – True when every directory yielded a match
    """
    found: List[Dict[str, str]] = []
    missing: List[str] = []

    for sim_dir in sim_dirs:
        search_root = Path(sim_dir) / search_subdir if search_subdir else Path(sim_dir)
        hit = _find_metric_file(str(search_root), metric_filename)
        if hit:
            found.append({"sim_dir": sim_dir, "file": hit})
        else:
            # Broader fallback: search the whole sim_dir
            hit = _find_metric_file(sim_dir, metric_filename)
            if hit:
                found.append({"sim_dir": sim_dir, "file": hit})
            else:
                missing.append(sim_dir)

    return {
        "success": len(missing) == 0,
        "found": found,
        "missing": missing,
        "n_found": len(found),
        "n_missing": len(missing),
    }


@tool
def plot_combined_overlay(
    data_files: List[str],
    labels: List[str],
    output_file: str,
    working_dir: str,
    title: str = "",
    xlabel: str = "Time (ns)",
    ylabel: str = "Value",
    colors: Optional[List[str]] = None,
    figsize: Tuple[int, int] = (10, 5),
    dpi: int = 200,
) -> Dict[str, Any]:
    """
    Overlay multiple 2-column data files on a single plot.

    All files must be parseable by ``_read_two_column_file`` (whitespace/CSV,
    ``#``-commented headers).  One line is drawn per file, coloured and labelled
    according to *labels*.

    Args:
        data_files: Ordered list of data file paths (one per simulation).
        labels: Human-readable legend labels, one per file.
        output_file: Output image filename (e.g. ``"rmsd_overlay.png"``).
            Saved inside *working_dir*.
        working_dir: Directory where the image is written.
        title: Plot title (optional).
        xlabel: X-axis label (default ``"Time (ns)"``).
        ylabel: Y-axis label (default ``"Value"``).
        colors: Optional list of Matplotlib colour strings.
        figsize: Figure size tuple (width, height) in inches.
        dpi: Image resolution.

    Returns:
        Dict with ``success``, ``output_path``, and per-file ``stats``.
    """
    if not HAS_MATPLOTLIB:
        return {"success": False, "error": "matplotlib not available"}
    if len(data_files) != len(labels):
        return {"success": False, "error": "data_files and labels must have the same length"}

    Path(working_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(working_dir) / output_file)

    default_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                      "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]
    if colors is None:
        colors = [default_colors[i % len(default_colors)] for i in range(len(data_files))]

    fig, ax = plt.subplots(figsize=figsize)
    per_file_stats: Dict[str, Dict] = {}
    errors: List[str] = []

    for fpath, label, color in zip(data_files, labels, colors):
        try:
            xs, ys = _read_two_column_file(fpath)
            ax.plot(xs, ys, label=label, color=color, linewidth=1.2, alpha=0.85)
            per_file_stats[label] = _float_stats(ys)
        except Exception as exc:
            errors.append(f"{label}: {exc}")
            logger.warning(f"plot_combined_overlay: skipping {fpath}: {exc}")

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    if title:
        ax.set_title(title)
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    logger.info(f"Saved overlay plot → {output_path}")
    return {
        "success": True,
        "output_path": output_path,
        "output_file": output_file,
        "stats": per_file_stats,
        "errors": errors or None,
    }


@tool
def compute_comparison_table(
    data_files: List[str],
    labels: List[str],
    output_csv: str,
    working_dir: str,
) -> Dict[str, Any]:
    """
    Compute mean/std/min/max for each simulation's metric file and write a CSV.

    Args:
        data_files: Ordered list of data file paths (column 1 = time/x, column 2 = metric).
        labels: Row labels (one per file), e.g. ``["1A", "2B", "3C"]``.
        output_csv: Output CSV filename (saved in *working_dir*).
        working_dir: Directory where the CSV is written.

    Returns:
        Dict with ``success``, ``output_path``, and ``table`` (list-of-dicts).
    """
    if len(data_files) != len(labels):
        return {"success": False, "error": "data_files and labels must have the same length"}

    Path(working_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(working_dir) / output_csv)

    rows: List[Dict[str, Any]] = []
    for fpath, label in zip(data_files, labels):
        row: Dict[str, Any] = {"simulation": label}
        try:
            _, ys = _read_two_column_file(fpath)
            row.update(_float_stats(ys))
        except Exception as exc:
            row.update({"mean": "N/A", "std": "N/A", "min": "N/A", "max": "N/A", "error": str(exc)})
            logger.warning(f"compute_comparison_table: cannot read {fpath}: {exc}")
        rows.append(row)

    if rows:
        fieldnames = list(rows[0].keys())
        with open(output_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    logger.info(f"Saved comparison table → {output_path}")
    return {
        "success": True,
        "output_path": output_path,
        "output_file": output_csv,
        "table": rows,
    }


@tool
def run_combined_analysis(
    sim_dirs: List[str],
    labels: List[str],
    working_dir: str,
    metrics: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    High-level convenience tool: collect metric files from all simulation
    directories, produce overlay plots and statistics CSV files for each metric.

    For every metric the tool will:
    1. Search each sim's ``analysis/`` sub-directory for a matching file.
    2. Create an overlay plot saved to ``{working_dir}/{metric}_overlay.png``.
    3. Write a stats CSV to ``{working_dir}/{metric}_stats.csv``.

    If a metric is missing in some simulations a warning is logged and the
    remaining simulations are still plotted.

    Args:
        sim_dirs: List of per-simulation root directories (e.g. ``["multi_run/1A",
            "multi_run/2B", "multi_run/3C"]``).
        labels: Human-readable labels for each simulation (same order as
            *sim_dirs*).
        working_dir: Output directory for all combined plots and tables.
        metrics: Metrics to process.  Defaults to
            ``["rmsd", "rmsf", "rg", "energy"]``.
            Each item is used as a filename pattern (e.g. ``"rmsd"`` matches
            ``rmsd.dat``, ``rmsd_ca.dat``, etc.).

    Returns:
        Dict with ``success``, ``plots`` (list of created image paths),
        ``tables`` (list of created CSV paths), and ``skipped`` (metrics
        where no data was found).
    """
    if metrics is None:
        metrics = ["rmsd", "rmsf", "rg", "energy"]

    # Metric → (filename pattern, x-label, y-label)
    _metric_meta: Dict[str, Tuple[str, str, str]] = {
        "rmsd":   ("rmsd",   "Time (ns)", "RMSD (Å)"),
        "rmsf":   ("rmsf",   "Residue",   "RMSF (Å)"),
        "rg":     ("rg",     "Time (ns)", "Rg (Å)"),
        "energy": ("energy", "Time (ns)", "Energy (kJ/mol)"),
        "sasa":   ("sasa",   "Time (ns)", "SASA (nm²)"),
        "hbond":  ("hbond",  "Time (ns)", "H-bonds"),
    }

    Path(working_dir).mkdir(parents=True, exist_ok=True)

    # Always create summary file so downstream reporter has a predictable input.
    try:
        from src.analysis.summary_logger import initialize_summary_file
        initialize_summary_file(working_dir)
    except Exception as init_exc:
        logger.warning(f"run_combined_analysis: could not initialize analysis_summary.jsonl: {init_exc}")

    plots: List[str] = []
    tables: List[str] = []
    skipped: List[str] = []
    # Track (metric, plot_path, table_path) for summary writing
    _processed: List[tuple] = []
    all_ok = True

    for metric in metrics:
        pattern, xlabel, ylabel = _metric_meta.get(
            metric.lower(), (metric, "X", metric.upper())
        )

        # Collect files
        collection = collect_metric_files.func(
            sim_dirs=sim_dirs,
            metric_filename=pattern,
            search_subdir="analysis",
        )

        found = collection.get("found", [])
        if len(found) < 2:
            logger.warning(f"run_combined_analysis: not enough data files for '{metric}' "
                           f"(found {len(found)}) — skipping")
            skipped.append(metric)
            continue

        # Keep only sims that have data; re-align labels
        active_files = [e["file"] for e in found]
        active_labels = []
        for e in found:
            idx = sim_dirs.index(e["sim_dir"]) if e["sim_dir"] in sim_dirs else len(active_labels)
            active_labels.append(labels[idx] if idx < len(labels) else e["sim_dir"])

        # Overlay plot
        plot_result = plot_combined_overlay.func(
            data_files=active_files,
            labels=active_labels,
            output_file=f"{metric}_overlay.png",
            working_dir=working_dir,
            title=f"{metric.upper()} Comparison",
            xlabel=xlabel,
            ylabel=ylabel,
        )
        plot_path = ""
        if plot_result.get("success"):
            plot_path = plot_result["output_path"]
            plots.append(plot_path)
        else:
            all_ok = False

        # Stats table
        table_result = compute_comparison_table.func(
            data_files=active_files,
            labels=active_labels,
            output_csv=f"{metric}_stats.csv",
            working_dir=working_dir,
        )
        table_path = ""
        if table_result.get("success"):
            table_path = table_result["output_path"]
            tables.append(table_path)
        else:
            all_ok = False

        _processed.append((metric, plot_path, table_path))

    # Write analysis_summary.jsonl so the reporter can read structured results
    try:
        from src.analysis.summary_logger import append_analysis_summary

        for metric, plot_path, table_path in _processed:
            # Re-read the CSV we just wrote to pull stats per simulation
            stats_per_sim: Dict[str, Any] = {}
            if table_path:
                try:
                    with open(table_path, newline="", encoding="utf-8") as fcsv:
                        import csv as _csv
                        reader = _csv.DictReader(fcsv)
                        for row in reader:
                            sim_label = row.pop("simulation", None) or row.pop("label", "?")
                            stats_per_sim[sim_label] = {
                                k: (float(v) if v not in ("N/A", "") else v)
                                for k, v in row.items()
                                if k not in ("error",)
                            }
                except Exception as csv_exc:
                    logger.warning(f"run_combined_analysis: could not re-read {table_path}: {csv_exc}")

            append_analysis_summary(
                working_dir=working_dir,
                analysis_type=f"Combined {metric.upper()}",
                statistics=stats_per_sim,
                files={k: v for k, v in {"overlay_plot": plot_path, "stats_csv": table_path}.items() if v},
                metadata={
                    "simulations": labels,
                    "n_simulations": len(labels),
                    "metric": metric,
                },
            )

        # Always add a run-level summary entry, even if every metric was skipped.
        append_analysis_summary(
            working_dir=working_dir,
            analysis_type="Combined_Analysis_Overview",
            statistics={
                "n_plots": len(plots),
                "n_tables": len(tables),
                "n_skipped_metrics": len(skipped),
            },
            files={},
            metadata={
                "simulations": labels,
                "metrics_requested": metrics,
                "metrics_skipped": skipped,
            },
        )
    except Exception as summary_exc:
        logger.warning(f"run_combined_analysis: could not write analysis_summary.jsonl: {summary_exc}")

    return {
        "success": all_ok,
        "plots": plots,
        "tables": tables,
        "skipped": skipped,
        "working_dir": working_dir,
        "summary": (
            f"Combined analysis complete: {len(plots)} plots, "
            f"{len(tables)} tables, {len(skipped)} metrics skipped."
        ),
    }
