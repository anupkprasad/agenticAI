"""
Combined Analysis Tools - Cross-simulation comparison utilities

Provides tools to collect metric data from multiple simulation directories,
produce overlay plots, and compute summary statistics tables.  Designed
for the "combined_analysis" phase of multi-simulation workflows.

Each function follows the same @tool convention used by the other modules
in src/analysis/ (returns a Dict[str, Any] with at least a "success" key).
"""
import os
import re
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
    x_col: int = 0,
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
            if len(parts) > max(x_col, y_col):
                try:
                    xs.append(float(parts[x_col]))
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
    x_col: int = 0,
    y_col: int = 1,
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
            xs, ys = _read_two_column_file(fpath, x_col=x_col, y_col=y_col)
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


@tool
def run_combined_dccm_analysis(
    sim_dirs: List[str],
    labels: List[str],
    working_dir: str,
    output_file: str = "dccm_comparison.png",
    vmin: float = -1.0,
    vmax: float = 1.0,
    dpi: int = 200,
) -> Dict[str, Any]:
    """
    Collect per-simulation DCCM CSV files and generate a side-by-side
    comparison heatmap for multi-simulation reports.

    Searches each simulation's ``analysis/`` sub-directory for a file whose
    name starts with ``"dccm"`` and ends with ``".csv"``.  The found CSV files
    are passed to ``plot_dccm_comparison`` to produce a single figure
    comparing the correlation matrices across all simulations.

    Args:
        sim_dirs: List of per-simulation root directories (same order as
            *labels*).
        labels: Human-readable labels for each simulation (one per sim_dir).
        working_dir: Output directory where the comparison figure is saved.
        output_file: Filename for the comparison PNG (default:
            ``"dccm_comparison.png"``).
        vmin: Colour scale minimum (default: −1.0).
        vmax: Colour scale maximum (default: +1.0).
        dpi: Image resolution (default: 200).

    Returns:
        Dict with ``success``, ``output_path``, ``found_files``,
        ``missing_sims``, and ``message``.
    """
    from src.analysis.dccm_calculator import plot_dccm_comparison as _plot_dccm

    Path(working_dir).mkdir(parents=True, exist_ok=True)

    found_files: List[str] = []
    found_labels: List[str] = []
    missing_sims: List[str] = []

    for sim_dir, label in zip(sim_dirs, labels):
        analysis_dir = Path(sim_dir) / "analysis"
        hit = None
        # Search analysis/ first, then the full sim_dir tree
        for search_root in [str(analysis_dir), sim_dir]:
            for p in sorted(Path(search_root).rglob("dccm*.csv")):
                hit = str(p)
                break
            if hit:
                break
        if hit:
            found_files.append(hit)
            found_labels.append(label)
        else:
            missing_sims.append(sim_dir)
            logger.warning(f"run_combined_dccm_analysis: no dccm CSV in {sim_dir}")

    if len(found_files) < 2:
        msg = (
            f"Not enough DCCM CSV files found "
            f"(need ≥2, found {len(found_files)}). "
            f"Missing: {missing_sims}"
        )
        logger.warning(msg)
        return {
            "success": False,
            "found_files": found_files,
            "missing_sims": missing_sims,
            "message": msg,
        }

    result = _plot_dccm.func(
        dccm_files=found_files,
        labels=found_labels,
        output_file=output_file,
        working_dir=working_dir,
        vmin=vmin,
        vmax=vmax,
        dpi=dpi,
    )

    # Write to analysis_summary.jsonl
    try:
        from src.analysis.summary_logger import append_analysis_summary
        append_analysis_summary(
            working_dir=working_dir,
            analysis_type="Combined_DCCM",
            statistics={"n_simulations_compared": len(found_files)},
            files={
                "comparison_figure": result.get("output_path", ""),
                "dccm_csv_files": found_files,
            },
            metadata={
                "simulations": found_labels,
                "missing_simulations": missing_sims,
            },
        )
    except Exception as se:
        logger.warning(f"run_combined_dccm_analysis: could not write summary: {se}")

    result["found_files"] = found_files
    result["missing_sims"] = missing_sims
    return result


@tool
def run_combined_dccm_difference(
    reference_sim_dir: str,
    compare_sim_dir: str,
    reference_label: str,
    compare_label: str,
    working_dir: str,
    output_prefix: str = "dccm_difference",
    plot_mode: str = "difference_only",
    diff_threshold: float = 0.3,
    dpi: int = 200,
) -> Dict[str, Any]:
    """
    Build a DCCM difference map between two simulations (e.g. protein-only vs protein+ATP).

    Locates ``dccm*.csv`` under each simulation's ``analysis/`` folder (from
    ``calculate_dccm``), then calls ``plot_dccm_difference`` with
    Δ = compare − reference.

    Args:
        reference_sim_dir: Baseline simulation root (protein-only).
        compare_sim_dir: Perturbed simulation root (e.g. protein + ATP + Mg).
        reference_label: Plot label for baseline.
        compare_label: Plot label for perturbed system.
        working_dir: Where difference CSV/PNG are written.
        output_prefix: Output filename prefix (default: ``dccm_difference``).
        plot_mode: ``difference_only`` or ``with_matrices``.
        diff_threshold: |ΔC| cutoff for reporting changed pairs.
        dpi: Figure resolution.

    Returns:
        Dict from ``plot_dccm_difference`` plus ``reference_csv`` / ``compare_csv`` paths.
    """
    from src.analysis.dccm_calculator import plot_dccm_difference as _plot_diff

    Path(working_dir).mkdir(parents=True, exist_ok=True)

    def _find_dccm_csv(sim_dir: str) -> Optional[str]:
        analysis_dir = Path(sim_dir) / "analysis"
        for search_root in [str(analysis_dir), sim_dir]:
            for p in sorted(Path(search_root).rglob("dccm*.csv")):
                return str(p)
        return None

    ref_csv = _find_dccm_csv(reference_sim_dir)
    cmp_csv = _find_dccm_csv(compare_sim_dir)
    if not ref_csv:
        return {
            "success": False,
            "message": f"No dccm CSV in reference sim: {reference_sim_dir}",
        }
    if not cmp_csv:
        return {
            "success": False,
            "message": f"No dccm CSV in compare sim: {compare_sim_dir}",
        }

    result = _plot_diff.func(
        reference_dccm_file=ref_csv,
        compare_dccm_file=cmp_csv,
        reference_label=reference_label,
        compare_label=compare_label,
        output_prefix=output_prefix,
        working_dir=working_dir,
        plot_mode=plot_mode,
        diff_threshold=diff_threshold,
        dpi=dpi,
    )
    result["reference_csv"] = ref_csv
    result["compare_csv"] = cmp_csv

    try:
        from src.analysis.summary_logger import append_analysis_summary
        append_analysis_summary(
            working_dir=working_dir,
            analysis_type="Combined_DCCM_Difference",
            statistics=result.get("delta_matrix_stats", {}),
            files=result.get("output_files", {}),
            metadata={
                "reference_sim_dir": reference_sim_dir,
                "compare_sim_dir": compare_sim_dir,
                "reference_label": reference_label,
                "compare_label": compare_label,
                "reference_csv": ref_csv,
                "compare_csv": cmp_csv,
            },
        )
    except Exception as se:
        logger.warning(f"run_combined_dccm_difference: summary log failed: {se}")

    return result


# ---------------------------------------------------------------------------
# RMSF segment bar plots & COM distance overlay
# ---------------------------------------------------------------------------

def parse_rmsf_segments_from_goal(text: str) -> List[Dict[str, Any]]:
    """
    Extract named protein residue ranges from a user goal string.

    Recognises patterns such as:
      - ``activation loop: 150 to 190``
      - ``residue range 150-190``
      - ``RMSF for residues 150 to 190``
    """
    if not text:
        return []

    segments: List[Dict[str, Any]] = []
    seen: set = set()

    def _add(name: str, start: int, end: int) -> None:
        if start > end:
            start, end = end, start
        key = (start, end)
        if key in seen or end - start < 1:
            return
        low_name = name.lower()
        if any(skip in low_name for skip in ("uniprot", "pdb:", "protein +")):
            return
        segments.append({
            "name": name.strip(),
            "residue_start": start,
            "residue_end": end,
        })
        seen.add(key)

    for m in re.finditer(
        r'([A-Za-z][A-Za-z0-9\s\-]{2,40}?)\s*:\s*(\d+)\s*(?:to|–|-|—)\s*(\d+)',
        text,
        re.IGNORECASE,
    ):
        _add(m.group(1), int(m.group(2)), int(m.group(3)))

    for m in re.finditer(
        r'(?:residue(?:s)?|resid(?:ue)?s?)\s+(?:range\s+)?(\d+)\s*(?:to|–|-|—)\s*(\d+)',
        text,
        re.IGNORECASE,
    ):
        _add("Residue segment", int(m.group(1)), int(m.group(2)))

    for m in re.finditer(
        r'(activation[\s\-]*loop|αC[\s\-]*helix|A[\s\-]*loop|'
        r'activation[\s\-]*segment|flexible[\s\-]*region)\s+'
        r'(\d+)\s*(?:to|–|-|—)\s*(\d+)',
        text,
        re.IGNORECASE,
    ):
        _add(m.group(1), int(m.group(2)), int(m.group(3)))

    return segments


def _read_rmsf_file(filepath: str) -> Tuple[List[int], List[float]]:
    """Read per-residue RMSF from .dat (tab/space) or two-column file."""
    residues: List[int] = []
    values: List[float] = []

    with open(filepath, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            raw = line.strip()
            if not raw or raw.startswith("#") or raw.startswith("@"):
                continue
            parts = raw.replace(",", "\t").split()
            if len(parts) < 2:
                continue
            try:
                residues.append(int(float(parts[0])))
                values.append(float(parts[1]))
            except ValueError:
                continue

    if not residues:
        raise ValueError(f"No RMSF data found in {filepath}")
    return residues, values


def _slugify_segment_name(name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "segment"


@tool
def plot_combined_rmsf_segment_bars(
    sim_dirs: List[str],
    labels: List[str],
    residue_start: int,
    residue_end: int,
    working_dir: str,
    segment_name: str = "Segment",
    output_file: Optional[str] = None,
    figsize: Tuple[int, int] = (12, 5),
    dpi: int = 200,
) -> Dict[str, Any]:
    """
    Grouped bar chart of per-residue RMSF within a residue range for all simulations.
    """
    if not HAS_MATPLOTLIB:
        return {"success": False, "error": "matplotlib not available"}

    if residue_start > residue_end:
        residue_start, residue_end = residue_end, residue_start

    Path(working_dir).mkdir(parents=True, exist_ok=True)
    slug = _slugify_segment_name(segment_name)
    out_name = output_file or f"rmsf_segment_{slug}_{residue_start}_{residue_end}.png"
    output_path = str(Path(working_dir) / out_name)

    series: List[Dict[str, Any]] = []
    missing: List[str] = []

    for sim_dir, label in zip(sim_dirs, labels):
        rmsf_file = _find_metric_file(str(Path(sim_dir) / "analysis"), "rmsf")
        if not rmsf_file:
            rmsf_file = _find_metric_file(sim_dir, "rmsf")
        if not rmsf_file:
            missing.append(label)
            continue
        try:
            res_ids, rmsf_vals = _read_rmsf_file(rmsf_file)
            filtered = {
                r: v for r, v in zip(res_ids, rmsf_vals)
                if residue_start <= r <= residue_end
            }
            if not filtered:
                missing.append(label)
                continue
            series.append({"label": label, "data": filtered})
        except Exception as exc:
            logger.warning(f"plot_combined_rmsf_segment_bars: {label}: {exc}")
            missing.append(label)

    if len(series) < 1:
        return {
            "success": False,
            "error": f"No RMSF data in residues {residue_start}-{residue_end}",
            "missing": missing,
        }

    all_residues = sorted({r for s in series for r in s["data"]})
    if not all_residues:
        return {"success": False, "error": "No residues in requested range"}

    n_res = len(all_residues)
    n_sims = len(series)
    x = list(range(n_res))
    width = 0.8 / max(n_sims, 1)
    default_colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
                      "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]

    fig, ax = plt.subplots(figsize=figsize)
    for i, s in enumerate(series):
        offset = (i - (n_sims - 1) / 2) * width
        ys = [s["data"].get(r, 0.0) for r in all_residues]
        ax.bar(
            [xi + offset for xi in x], ys, width=width,
            label=s["label"],
            color=default_colors[i % len(default_colors)],
            alpha=0.88,
        )

    step = max(1, n_res // 12)
    tick_pos = list(range(0, n_res, step))
    tick_labels = [str(all_residues[i]) for i in tick_pos]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_labels, rotation=45, ha="right", fontsize=8)
    ax.set_xlabel("Residue", fontsize=10)
    ax.set_ylabel("RMSF (Å)", fontsize=10)
    ax.set_title(
        f"RMSF — {segment_name} (residues {residue_start}–{residue_end})",
        fontsize=11, fontweight="bold",
    )
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return {
        "success": True,
        "output_path": output_path,
        "segment_name": segment_name,
        "residue_start": residue_start,
        "residue_end": residue_end,
        "n_simulations": len(series),
        "missing": missing,
        "message": (
            f"RMSF segment bar plot for {segment_name} "
            f"({residue_start}–{residue_end}) saved to {output_path}"
        ),
    }


@tool
def run_combined_rmsf_segment_analysis(
    sim_dirs: List[str],
    labels: List[str],
    working_dir: str,
    user_goal: Optional[str] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Generate RMSF bar plots for residue segments specified in the user goal."""
    Path(working_dir).mkdir(parents=True, exist_ok=True)

    seg_list = segments or parse_rmsf_segments_from_goal(user_goal or "")
    if not seg_list:
        return {
            "success": False,
            "plots": [],
            "segments": [],
            "message": "No RMSF residue segments found in user goal",
        }

    plots: List[str] = []
    processed: List[Dict[str, Any]] = []

    for seg in seg_list:
        result = plot_combined_rmsf_segment_bars.func(
            sim_dirs=sim_dirs,
            labels=labels,
            residue_start=int(seg["residue_start"]),
            residue_end=int(seg["residue_end"]),
            working_dir=working_dir,
            segment_name=seg.get("name", "Segment"),
        )
        entry = {
            "segment": seg,
            "success": result.get("success", False),
            "output_path": result.get("output_path", ""),
        }
        processed.append(entry)
        if result.get("success"):
            plots.append(result["output_path"])

    try:
        from src.analysis.summary_logger import append_analysis_summary
        append_analysis_summary(
            working_dir=working_dir,
            analysis_type="Combined_RMSF_Segments",
            statistics={"n_segments": len(processed), "n_plots": len(plots)},
            files={"segment_plots": plots},
            metadata={"segments": seg_list, "results": processed},
        )
    except Exception as se:
        logger.warning(f"run_combined_rmsf_segment_analysis: summary log failed: {se}")

    return {
        "success": len(plots) > 0,
        "plots": plots,
        "segments": seg_list,
        "results": processed,
        "message": f"Generated {len(plots)} RMSF segment bar plot(s)",
    }


@tool
def run_combined_com_distance_analysis(
    sim_dirs: List[str],
    labels: List[str],
    working_dir: str,
    output_file: str = "com_distance_overlay.png",
) -> Dict[str, Any]:
    """
    Overlay ATP–catalytic-pocket COM distance time series across simulations.
    """
    Path(working_dir).mkdir(parents=True, exist_ok=True)

    found_files: List[str] = []
    found_labels: List[str] = []
    missing: List[str] = []

    for sim_dir, label in zip(sim_dirs, labels):
        analysis_dir = Path(sim_dir) / "analysis"
        hit = None
        for pattern in ("ligand_pocket_distance", "com_distance"):
            for search_root in [str(analysis_dir), sim_dir]:
                hit = _find_metric_file(search_root, pattern)
                if hit:
                    break
            if hit:
                break
        if hit:
            found_files.append(hit)
            found_labels.append(label)
        else:
            missing.append(label)

    if len(found_files) < 1:
        return {
            "success": False,
            "message": (
                "No ligand pocket / COM distance CSV found in any simulation. "
                f"Missing: {missing}"
            ),
            "missing": missing,
        }

    result = plot_combined_overlay.func(
        data_files=found_files,
        labels=found_labels,
        output_file=output_file,
        working_dir=working_dir,
        title="ATP–Catalytic Pocket COM Distance",
        xlabel="Time (ns)",
        ylabel="COM Distance (Å)",
        x_col=1,
        y_col=2,
    )

    if result.get("success"):
        try:
            from src.analysis.summary_logger import append_analysis_summary
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Combined_COM_Distance",
                statistics=result.get("stats", {}),
                files={
                    "overlay_plot": result.get("output_path", ""),
                    "source_csv_files": found_files,
                },
                metadata={
                    "simulations": found_labels,
                    "missing_simulations": missing,
                },
            )
        except Exception as se:
            logger.warning(f"run_combined_com_distance_analysis: summary failed: {se}")

    result["missing"] = missing
    result["found_files"] = found_files
    return result

