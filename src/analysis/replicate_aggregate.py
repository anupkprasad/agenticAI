"""Aggregate per-replicate analysis metrics into ``analysis/avg/`` (mean ± std).

Does **not** average trajectory coordinates — only scalar/time-series metrics.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from langchain_core.tools import tool

from src.analysis.replicate_paths import (
    analysis_avg_dir,
    discover_analysis_rep_dirs,
    format_rep_id,
    iter_rep_ids,
    normalize_rep_num,
    parse_rep_id,
)

logger = logging.getLogger(__name__)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except Exception:
    HAS_MPL = False


def _read_xy(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    xs: List[float] = []
    ys: List[float] = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("@"):
                continue
            parts = s.replace(",", " ").split()
            if len(parts) < 2:
                continue
            try:
                xs.append(float(parts[0]))
                ys.append(float(parts[1]))
            except ValueError:
                continue
    if not xs:
        raise ValueError(f"No numeric columns in {path}")
    return np.asarray(xs, dtype=float), np.asarray(ys, dtype=float)


def _align_series(
    series: Sequence[Tuple[np.ndarray, np.ndarray]],
) -> Tuple[np.ndarray, np.ndarray]:
    """Truncate to shortest length; use first series' x as the common grid."""
    n = min(len(y) for _, y in series)
    if n < 2:
        raise ValueError("Need ≥2 points after alignment")
    x0 = series[0][0][:n]
    mat = np.vstack([y[:n] for _, y in series])
    return x0, mat


def _find_metric_in_dir(adir: Path, metric_filename: str) -> Optional[Path]:
    exact = adir / metric_filename
    if exact.is_file():
        return exact
    stem = Path(metric_filename).stem
    for cand in sorted(adir.rglob("*")):
        if not cand.is_file():
            continue
        if cand.name == metric_filename or stem in cand.stem:
            if cand.suffix.lower() in {".dat", ".xvg", ".csv", ".txt"}:
                return cand
    return None


@tool
def aggregate_replicate_metrics(
    sim_dir: str,
    metric_filenames: Optional[List[str]] = None,
    rep_num: Optional[int] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Average analysis metrics across ``analysis/repXX/`` into ``analysis/avg/``.

    For each metric file (e.g. ``rmsd.dat``): write mean/std columns, optional
    overlay PNG, and update ``summary_scalars.json``. Does not average .xtc coords.

    Args:
        sim_dir: Simulation root (parent of ``analysis/``).
        metric_filenames: Basenames to aggregate; default discovers common .dat/.xvg.
        rep_num: Expected N (optional; discovery uses existing ``repXX`` dirs).
        working_dir: Ignored alias (executor may inject analysis path).
    """
    del working_dir  # executor may force this; sim_dir is authoritative
    root = Path(sim_dir)
    if not root.is_dir():
        return {"success": False, "error": f"sim_dir not found: {sim_dir}"}

    rep_dirs = discover_analysis_rep_dirs(root)
    # Drop flat analysis/ when nested reps exist
    nested = [d for d in rep_dirs if parse_rep_id(d.name) is not None]
    if nested:
        rep_dirs = nested
    if rep_num:
        want = set(iter_rep_ids(rep_num))
        rep_dirs = [d for d in rep_dirs if d.name in want] or nested
    if len(rep_dirs) < 2 and normalize_rep_num(rep_num or 1) < 2:
        return {
            "success": True,
            "skipped": True,
            "message": "rep_num≤1 or fewer than 2 rep dirs — nothing to average",
            "n_reps": len(rep_dirs),
        }
    if len(rep_dirs) < 2:
        return {
            "success": False,
            "error": f"Need ≥2 replicate analysis dirs, found {len(rep_dirs)}",
            "rep_dirs": [str(d) for d in rep_dirs],
        }

    if not metric_filenames:
        names = set()
        for d in rep_dirs:
            for p in d.iterdir():
                if p.is_file() and p.suffix.lower() in {".dat", ".xvg", ".csv"}:
                    names.add(p.name)
        metric_filenames = sorted(names)

    avg = analysis_avg_dir(root)
    avg.mkdir(parents=True, exist_ok=True)
    scalars: Dict[str, Any] = {"n_reps": len(rep_dirs), "reps": [d.name for d in rep_dirs]}
    written: List[str] = []
    errors: List[str] = []

    for name in metric_filenames:
        paths = []
        for d in rep_dirs:
            hit = _find_metric_in_dir(d, name)
            if hit:
                paths.append((d.name, hit))
        if len(paths) < 2:
            errors.append(f"{name}: found in {len(paths)} reps")
            continue
        try:
            series = [_read_xy(p) for _, p in paths]
            x, mat = _align_series(series)
            mean = mat.mean(axis=0)
            std = mat.std(axis=0, ddof=1) if mat.shape[0] > 1 else np.zeros_like(mean)
            stem = Path(name).stem
            out_dat = avg / f"{stem}_mean_std.dat"
            with out_dat.open("w", encoding="utf-8") as fh:
                fh.write(f"# aggregated from {len(paths)} replicates\n")
                fh.write("# time  mean  std\n")
                for xi, mi, si in zip(x, mean, std):
                    fh.write(f"{xi:.6f}  {mi:.6f}  {si:.6f}\n")
            # Also write stem.dat as mean-only for combined collectors expecting rmsd.dat
            compat = avg / name
            with compat.open("w", encoding="utf-8") as fh:
                fh.write(f"# mean across {len(paths)} replicates\n")
                for xi, mi in zip(x, mean):
                    fh.write(f"{xi:.6f}  {mi:.6f}\n")
            written.extend([str(out_dat), str(compat)])
            scalars[stem] = {
                "mean_of_mean": float(np.mean(mean)),
                "std_of_mean": float(np.std(mean)),
                "n_reps": len(paths),
            }
            if HAS_MPL:
                fig, ax = plt.subplots(figsize=(8, 4))
                for (rid, _), (_, y) in zip(paths, series):
                    ax.plot(x, y[: len(x)], alpha=0.35, linewidth=0.9, label=rid)
                ax.plot(x, mean, color="black", linewidth=1.6, label="mean")
                ax.fill_between(x, mean - std, mean + std, color="gray", alpha=0.25, label="±1σ")
                ax.set_title(f"{stem} (n={len(paths)})")
                ax.legend(fontsize=7, loc="best")
                fig.tight_layout()
                png = avg / f"{stem}_overlay.png"
                fig.savefig(png, dpi=150)
                plt.close(fig)
                written.append(str(png))
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning("aggregate_replicate_metrics failed for %s: %s", name, exc)

    summary_path = avg / "summary_scalars.json"
    summary_path.write_text(json.dumps(scalars, indent=2) + "\n", encoding="utf-8")
    written.append(str(summary_path))

    return {
        "success": len(written) > 0 and len(errors) < len(metric_filenames or []),
        "avg_dir": str(avg),
        "n_reps": len(rep_dirs),
        "written": written,
        "errors": errors,
        "scalars": scalars,
    }
