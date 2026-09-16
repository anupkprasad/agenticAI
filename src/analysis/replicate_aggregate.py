"""Aggregate per-replicate analysis metrics into ``analysis/avg/`` (mean ± std).

Does **not** average trajectory coordinates — only scalar/time-series metrics
and supported multi-column / matrix products (DCCM, PCA, FEL grid).

Non-aggregatable catalogs (basin tables, structure lists) are skipped so we
never emit misleading 1D “overlay” line plots for them.
"""
from __future__ import annotations

import csv
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from langchain_core.tools import tool

from src.analysis.replicate_paths import (
    analysis_avg_dir,
    discover_analysis_rep_dirs,
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

# Common 1D products expected under analysis/repXX/ for post collectors.
COMMON_METRIC_BASENAMES: Tuple[str, ...] = (
    "rmsd.dat",
    "rmsf.dat",
    "rg.dat",
    "gyrate.dat",
    "gyration.dat",
    "sasa.dat",
    "dccm.dat",
    "dccm.csv",
    "dccm_matrix.dat",
    "ligand_rmsd.dat",
    "ligand_rmsf.dat",
    "pocket_rmsf.dat",
    "ligand_pocket_distance.csv",
    "ligand_pocket_distance.dat",
    "com_distance.dat",
    "com_distance.csv",
    "hbonds.dat",
    "energy.dat",
    "pca_projections.dat",
    "pca_variance.dat",
    "fel_pc1_pc2_grid.csv",
)

# Basenames that must not be treated as XY series (catalog / metadata tables).
SKIP_BASENAMES = frozenset(
    {
        "fel_basins.csv",
        "fel_basin_structures.csv",
        "fel_features.csv",
        "fel_features.json",
        "nearby_residues.json",
        "nearby_residues.csv",
        "analysis_summary.jsonl",
        "summary_scalars.json",
    }
)


def _classify_metric(path: Path) -> str:
    """Return aggregation kind: series | dccm | pca_proj | pca_var | fel_grid | skip | matrix."""
    name = path.name.lower()
    if name in SKIP_BASENAMES or name.endswith(".json") or name.endswith(".jsonl"):
        return "skip"
    if "dccm" in name:
        return "dccm"
    # Independent per-rep PCA / dihedral-PCA projections are not commensurate
    # across replicates — skip averaging (shared-ref PCA is the right path).
    if name in {"projections.npy", "pca_projections.npy", "tica_projections.npy"} or (
        "projection" in name and name.endswith(".npy")
    ):
        return "pca_proj"
    if "pca_proj" in name:
        return "pca_proj"
    if "pca_var" in name:
        return "pca_var"
    if "fel_pc1_pc2_grid" in name or (
        "fel" in name and "grid" in name and name.endswith(".csv")
    ):
        return "fel_grid"
    if "basin" in name or name.startswith("fel_features"):
        return "skip"
    if name.endswith(".npy") or "matrix" in name:
        return "matrix"
    return "series"


def _pick_xy_column_indices(header: Sequence[str], n_cols: int) -> Tuple[int, int]:
    """Choose (x, y) columns for time-series CSVs (prefer time vs distance/COM)."""
    lower = [h.strip().lower() for h in header]
    skip_y = {
        "frame", "frames", "frame_index", "index",
        "time_ns", "time", "t_ns", "time (ns)", "time_ps",
    }
    xi: Optional[int] = None
    for i, name in enumerate(lower):
        if name in ("time_ns", "time (ns)", "t_ns", "time_ps") or (
            "time" in name and "frame" not in name
        ):
            xi = i
            break
    if xi is None and n_cols >= 3 and lower and lower[0] in (
        "frame", "frames", "frame_index", "index"
    ):
        xi = 1
    if xi is None:
        xi = 0

    y_priority = (
        "distance_angstrom",
        "distance_a",
        "distance",
        "com_distance",
        "com",
        "sasa_nm2",
        "sasa",
        "rmsd",
        "rmsf",
        "rg",
        "gyration",
        "energy",
        "value",
        "n_contacts",
        "n_hbonds",
    )
    for pat in y_priority:
        for i, name in enumerate(lower):
            if i == xi or name in skip_y:
                continue
            if name == pat or (len(pat) > 3 and pat in name):
                return xi, i

    # 3-col frame,time,metric → use last column as y
    if n_cols >= 3 and xi < n_cols - 1:
        return xi, n_cols - 1
    yi = 1 if n_cols > 1 and xi == 0 else (0 if xi != 0 else min(1, n_cols - 1))
    if yi == xi and n_cols > 1:
        yi = 1 if xi == 0 else 0
    return xi, yi


def _read_xy(path: Path) -> Tuple[np.ndarray, np.ndarray]:
    """Load an XY series; for ``frame,time,distance`` CSVs use time vs distance."""
    xs: List[float] = []
    ys: List[float] = []
    header: List[str] = []
    xi, yi = 0, 1
    convert_x_to_ns = False
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            s = line.strip()
            if not s:
                continue
            if s.startswith("#") or s.startswith("@"):
                low = s.lower()
                if "(ps)" in low or 'label "time (ps)"' in low or "time(ps)" in low.replace(" ", ""):
                    convert_x_to_ns = True
                continue
            parts = s.replace(",", " ").split()
            if not parts:
                continue
            # CSV / whitespace header
            first = parts[0]
            try:
                float(first)
            except ValueError:
                if not header and any(c.isalpha() for c in first):
                    raw = [p.strip() for p in s.split(",")] if "," in s else parts
                    header = raw
                    xi, yi = _pick_xy_column_indices(header, max(len(header), 2))
                    h0 = header[xi].lower() if xi < len(header) else ""
                    if "(ps)" in h0 or "time_ps" in h0 or "time(ps)" in h0.replace(" ", ""):
                        convert_x_to_ns = True
                continue
            if len(parts) <= max(xi, yi):
                continue
            try:
                xs.append(float(parts[xi]))
                ys.append(float(parts[yi]))
            except ValueError:
                continue
    if not xs:
        raise ValueError(f"No numeric columns in {path}")
    x_arr = np.asarray(xs, dtype=float)
    if convert_x_to_ns:
        x_arr = x_arr / 1000.0
    return x_arr, np.asarray(ys, dtype=float)


def _read_matrix(path: Path) -> np.ndarray:
    """Load a dense numeric matrix (.dat/.csv/.npy) for element-wise averaging."""
    if path.suffix.lower() == ".npy":
        mat = np.load(str(path))
        if mat.ndim != 2:
            raise ValueError(f"Expected 2D array in {path}, got shape {mat.shape}")
        return np.asarray(mat, dtype=float)

    rows: List[List[float]] = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        for line in fh:
            s = line.strip()
            if not s or s.startswith("#") or s.startswith("@"):
                continue
            parts = s.replace(",", " ").split()
            try:
                vals = [float(p) for p in parts]
            except ValueError:
                continue
            if len(vals) >= 2:
                rows.append(vals)
    if not rows:
        raise ValueError(f"No numeric matrix rows in {path}")
    w = min(len(r) for r in rows)
    mat = np.asarray([r[:w] for r in rows], dtype=float)
    if mat.ndim != 2 or mat.shape[0] < 2 or mat.shape[1] < 2:
        raise ValueError(f"Matrix too small in {path}: {mat.shape}")
    return mat


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
    """Locate ``metric_filename`` by exact basename only (no stem fuzzy match)."""
    exact = adir / metric_filename
    if exact.is_file():
        return exact
    for cand in sorted(adir.rglob(metric_filename)):
        if cand.is_file():
            return cand
    return None


def _discover_metric_names(rep_dirs: List[Path]) -> List[str]:
    names: set = set()
    for d in rep_dirs:
        for p in d.iterdir():
            if p.is_file() and p.suffix.lower() in {".dat", ".xvg", ".csv", ".npy"}:
                if p.name.lower() not in SKIP_BASENAMES:
                    names.add(p.name)
        for sub in d.iterdir():
            if not sub.is_dir():
                continue
            for p in sub.iterdir():
                if p.is_file() and p.suffix.lower() in {".dat", ".xvg", ".csv", ".npy"}:
                    if p.name.lower() not in SKIP_BASENAMES:
                        names.add(p.name)
    for common in COMMON_METRIC_BASENAMES:
        if any(_find_metric_in_dir(d, common) for d in rep_dirs):
            names.add(common)
    return sorted(names)


def _aggregate_xy_metric(
    name: str,
    paths: List[Tuple[str, Path]],
    avg: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    series = [_read_xy(p) for _, p in paths]
    x, mat = _align_series(series)
    mean = mat.mean(axis=0)
    std = mat.std(axis=0, ddof=1) if mat.shape[0] > 1 else np.zeros_like(mean)
    stem = Path(name).stem
    written: List[str] = []
    out_dat = avg / f"{stem}_mean_std.dat"
    with out_dat.open("w", encoding="utf-8") as fh:
        fh.write(f"# aggregated from {len(paths)} replicates\n")
        fh.write("# x  mean  std\n")
        for xi, mi, si in zip(x, mean, std):
            fh.write(f"{xi:.6f}  {mi:.6f}  {si:.6f}\n")
    compat = avg / name
    with compat.open("w", encoding="utf-8") as fh:
        fh.write(f"# mean across {len(paths)} replicates\n")
        for xi, mi in zip(x, mean):
            fh.write(f"{xi:.6f}  {mi:.6f}\n")
    written.extend([str(out_dat), str(compat)])
    scalars = {
        "mean_of_mean": float(np.mean(mean)),
        "std_of_mean": float(np.std(mean)),
        "n_reps": len(paths),
        "kind": "series",
    }
    if HAS_MPL:
        fig, ax = plt.subplots(figsize=(8, 4))
        for (rid, _), (_, y) in zip(paths, series):
            ax.plot(x, y[: len(x)], alpha=0.35, linewidth=0.9, label=rid)
        ax.plot(x, mean, color="black", linewidth=1.6, label="mean")
        ax.set_title(f"{stem} (n={len(paths)})")
        # Prefer ns when the series looks like MD time already converted
        if float(np.nanmax(x)) <= 5000:
            ax.set_xlabel("Time (ns)")
        else:
            ax.set_xlabel("x")
        ax.legend(fontsize=7, loc="best")
        fig.tight_layout()
        png = avg / f"{stem}_overlay.png"
        fig.savefig(png, dpi=150)
        plt.close(fig)
        written.append(str(png))
    return written, scalars


def _aggregate_dense_matrix(
    name: str,
    paths: List[Tuple[str, Path]],
    avg: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    mats = [_read_matrix(p) for _, p in paths]
    nr = min(m.shape[0] for m in mats)
    nc = min(m.shape[1] for m in mats)
    mats = [m[:nr, :nc] for m in mats]
    stack = np.stack(mats, axis=0)
    mean = stack.mean(axis=0)
    std = stack.std(axis=0, ddof=1) if stack.shape[0] > 1 else np.zeros_like(mean)
    stem = Path(name).stem
    written: List[str] = []
    out_mean = avg / name
    if Path(name).suffix.lower() == ".npy":
        np.save(str(out_mean), mean)
        np.save(str(avg / f"{stem}_std.npy"), std)
        written.extend([str(out_mean), str(avg / f"{stem}_std.npy")])
    else:
        np.savetxt(str(out_mean), mean, fmt="%.6f")
        np.savetxt(str(avg / f"{stem}_std.dat"), std, fmt="%.6f")
        written.extend([str(out_mean), str(avg / f"{stem}_std.dat")])
    scalars = {
        "mean_of_abs": float(np.mean(np.abs(mean))),
        "n_reps": len(paths),
        "shape": list(mean.shape),
        "kind": "matrix",
    }
    if HAS_MPL:
        from src.analysis.feature_matrix_plots import save_feature_matrix_png

        png = avg / f"{stem}_mean.png"
        saved = save_feature_matrix_png(
            mean,
            png,
            title=f"{stem} mean (n={len(paths)})",
            std_mat=std,
        )
        if saved:
            written.append(saved)
        # Prefer heatmap name over legacy line overlay
        legacy = avg / f"{stem}_overlay.png"
        if legacy.is_file():
            try:
                legacy.unlink()
            except OSError:
                pass
    return written, scalars


def _aggregate_dccm(
    name: str,
    paths: List[Tuple[str, Path]],
    avg: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """Average long-format DCCM CSVs (residue_i, residue_j, correlation) → heatmap."""
    from src.analysis.dccm_calculator import _load_dccm_csv

    loaded: List[Tuple[str, np.ndarray, List[int]]] = []
    for rid, p in paths:
        # Dense matrix fallback if not long-format CSV
        text_head = ""
        try:
            with p.open("r", encoding="utf-8", errors="ignore") as fh:
                text_head = fh.readline().lower()
        except OSError:
            text_head = ""
        if "residue_i" in text_head or p.suffix.lower() == ".csv":
            try:
                mat, resids = _load_dccm_csv(str(p))
                loaded.append((rid, mat, list(resids)))
                continue
            except Exception as exc:
                logger.warning("DCCM CSV load failed for %s: %s — trying dense", p, exc)
        mat = _read_matrix(p)
        loaded.append((rid, mat, list(range(1, mat.shape[0] + 1))))

    # Intersection of residue IDs across reps
    common = set(loaded[0][2])
    for _, _, resids in loaded[1:]:
        common &= set(resids)
    if len(common) < 3:
        raise ValueError("DCCM reps share fewer than 3 residue IDs")
    common_ids = sorted(common)

    mats = []
    for _, mat, resids in loaded:
        idx = {r: i for i, r in enumerate(resids)}
        sel = [idx[r] for r in common_ids]
        mats.append(mat[np.ix_(sel, sel)])
    stack = np.stack(mats, axis=0)
    mean = stack.mean(axis=0)
    std = stack.std(axis=0, ddof=1) if stack.shape[0] > 1 else np.zeros_like(mean)

    written: List[str] = []
    out_csv = avg / "dccm.csv"
    with out_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["residue_i", "residue_j", "correlation"])
        n = len(common_ids)
        for i in range(n):
            for j in range(n):
                w.writerow([common_ids[i], common_ids[j], f"{mean[i, j]:.6f}"])
    written.append(str(out_csv))

    std_csv = avg / "dccm_std.csv"
    with std_csv.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["residue_i", "residue_j", "std"])
        n = len(common_ids)
        for i in range(n):
            for j in range(n):
                w.writerow([common_ids[i], common_ids[j], f"{std[i, j]:.6f}"])
    written.append(str(std_csv))

    # Remove bogus XY dumps from older aggregator runs
    for junk in ("dccm_mean_std.dat", "dccm_overlay.png"):
        jp = avg / junk
        if jp.is_file():
            try:
                jp.unlink()
            except OSError:
                pass

    scalars = {
        "n_reps": len(paths),
        "n_residues": len(common_ids),
        "mean_abs_corr": float(np.mean(np.abs(mean))),
        "kind": "dccm",
    }
    if HAS_MPL:
        fig, ax = plt.subplots(figsize=(6, 5))
        im = ax.imshow(
            mean,
            cmap="coolwarm",
            vmin=-1,
            vmax=1,
            origin="lower",
            aspect="equal",
        )
        fig.colorbar(im, ax=ax, fraction=0.046, label="correlation")
        ax.set_title(f"DCCM mean (n={len(paths)})")
        ax.set_xlabel("residue index")
        ax.set_ylabel("residue index")
        # Sparse tick labels from residue IDs
        if len(common_ids) <= 20:
            ticks = list(range(len(common_ids)))
        else:
            step = max(1, len(common_ids) // 8)
            ticks = list(range(0, len(common_ids), step))
        ax.set_xticks(ticks)
        ax.set_yticks(ticks)
        ax.set_xticklabels([str(common_ids[i]) for i in ticks], fontsize=7, rotation=45)
        ax.set_yticklabels([str(common_ids[i]) for i in ticks], fontsize=7)
        fig.tight_layout()
        png = avg / "dccm_mean.png"
        fig.savefig(png, dpi=150)
        plt.close(fig)
        written.append(str(png))
        # Also write dccm_overlay.png as the heatmap so collectors find a plot
        overlay = avg / "dccm_overlay.png"
        import shutil

        shutil.copy2(png, overlay)
        written.append(str(overlay))
    return written, scalars


def _aggregate_pca_projections(
    name: str,
    paths: List[Tuple[str, Path]],
    avg: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """Skip frame-wise PCA projection averages from independent per-rep PCAs.

    Per-rep PC1/PC2 spaces are not commensurate; a pointwise mean path lands
    in empty space between clusters. Prefer pre_combined shared-reference PCA
    / FEL, then average those aligned projections.
    """
    del name, paths
    for junk in (
        "pca_projections.dat",
        "pca_projections_std.dat",
        "pca_projections_mean_std.dat",
        "pca_projections_overlay.png",
    ):
        jp = avg / junk
        if jp.is_file():
            try:
                jp.unlink()
            except OSError:
                pass
    return [], {
        "skipped": True,
        "kind": "pca_proj",
        "reason": (
            "independent per-rep PCA spaces; use pre_combined shared-reference "
            "PCA then average aligned projections"
        ),
    }


def _aggregate_pca_variance(
    name: str,
    paths: List[Tuple[str, Path]],
    avg: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    series = []
    for rid, p in paths:
        pcs: List[float] = []
        vars_: List[float] = []
        with p.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                parts = s.replace(",", " ").split()
                if len(parts) < 2:
                    continue
                try:
                    pcs.append(float(parts[0]))
                    vars_.append(float(parts[1]))
                except ValueError:
                    continue
        series.append((rid, np.asarray(pcs), np.asarray(vars_)))
    n = min(len(v) for _, _, v in series)
    x = series[0][1][:n]
    mat = np.vstack([v[:n] for _, _, v in series])
    mean = mat.mean(axis=0)
    std = mat.std(axis=0, ddof=1) if mat.shape[0] > 1 else np.zeros_like(mean)

    written: List[str] = []
    out = avg / name
    with out.open("w", encoding="utf-8") as fh:
        fh.write("# PC\tvariance_A2\tstd\n")
        for xi, mi, si in zip(x, mean, std):
            fh.write(f"{int(xi)}\t{mi:.6f}\t{si:.6f}\n")
    written.append(str(out))

    for junk in (f"{Path(name).stem}_mean_std.dat", f"{Path(name).stem}_overlay.png"):
        jp = avg / junk
        if jp.is_file():
            try:
                jp.unlink()
            except OSError:
                pass

    scalars = {
        "n_reps": len(paths),
        "kind": "pca_var",
        "top_pc_variance": float(mean[0]) if len(mean) else None,
    }
    if HAS_MPL:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar(x, mean, yerr=std, color="steelblue", alpha=0.85, ecolor="gray", capsize=3)
        ax.set_xlabel("PC")
        ax.set_ylabel("variance")
        ax.set_title(f"PCA variance mean (n={len(paths)})")
        fig.tight_layout()
        png = avg / "pca_variance_overlay.png"
        fig.savefig(png, dpi=150)
        plt.close(fig)
        written.append(str(png))
    return written, scalars


def _aggregate_fel_grid(
    name: str,
    paths: List[Tuple[str, Path]],
    avg: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    """FEL grids from independent per-rep PCAs are not commensurate — skip.

    Shared-reference FEL (pre_combined / reference landscape) is the correct
    path for cross-rep FEL averaging; raw ``fel_pc1_pc2_grid.csv`` files live
    in different PC spaces per replicate.
    """
    del name, paths
    for junk in (
        "fel_pc1_pc2_grid.csv",
        "fel_pc1_pc2_grid_mean_std.dat",
        "fel_pc1_pc2_grid_overlay.png",
        "fel_basins.csv",
        "fel_basins_mean_std.dat",
        "fel_basins_overlay.png",
        "fel_basin_structures.csv",
        "fel_basin_structures_mean_std.dat",
        "fel_basin_structures_overlay.png",
    ):
        jp = avg / junk
        if jp.is_file():
            try:
                jp.unlink()
            except OSError:
                pass
    return [], {
        "skipped": True,
        "kind": "fel_grid",
        "reason": "per-rep FEL grids use independent PCA spaces; use shared-reference FEL",
    }


def _cleanup_avg_junk(avg: Path) -> None:
    """Remove misleading overlays left by older XY-only aggregation."""
    patterns = (
        "fel_basins*",
        "fel_basin_structures*",
        "fel_features*",
        "*_mean_std.dat",
    )
    # Keep intentional mean_std for true 1D series (rmsd/rmsf/…) — only purge
    # known bad stems from prior runs.
    bad_stems = {
        "dccm_mean_std",
        "fel_basins",
        "fel_basin_structures",
        "fel_pc1_pc2_grid",
        "pca_projections_mean_std",
    }
    for p in list(avg.iterdir()) if avg.is_dir() else []:
        if not p.is_file():
            continue
        stem = p.stem.lower()
        name = p.name.lower()
        if name.startswith("fel_basins") or name.startswith("fel_basin_structures"):
            try:
                p.unlink()
            except OSError:
                pass
            continue
        if stem in bad_stems or any(stem.startswith(b) for b in bad_stems):
            try:
                p.unlink()
            except OSError:
                pass



def _dispatch_aggregate(
    name: str,
    paths: List[Tuple[str, Path]],
    avg: Path,
) -> Tuple[List[str], Dict[str, Any]]:
    kind = _classify_metric(paths[0][1])
    if kind == "skip":
        return [], {"skipped": True, "kind": "skip", "n_reps": len(paths)}
    if kind == "dccm":
        return _aggregate_dccm(name, paths, avg)
    if kind == "pca_proj":
        return _aggregate_pca_projections(name, paths, avg)
    if kind == "pca_var":
        return _aggregate_pca_variance(name, paths, avg)
    if kind == "fel_grid":
        return _aggregate_fel_grid(name, paths, avg)
    if kind == "matrix":
        return _aggregate_dense_matrix(name, paths, avg)
    return _aggregate_xy_metric(name, paths, avg)


@tool
def aggregate_replicate_metrics(
    sim_dir: str,
    metric_filenames: Optional[List[str]] = None,
    rep_num: Optional[int] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Average analysis metrics across ``analysis/repXX/`` into ``analysis/avg/``.

    Handles 1D series (RMSD/RMSF/…), long-format DCCM → heatmap, PCA
    projections (PC1–PC2 path), PCA variance bars, and FEL grids when aligned.
    Skips basin/feature catalog tables. Does not average .xtc coords.

    Args:
        sim_dir: Simulation root (parent of ``analysis/``).
        metric_filenames: Basenames to aggregate; default discovers common files.
        rep_num: Expected N (optional; discovery uses existing ``repXX`` dirs).
        working_dir: Ignored alias (executor may inject analysis path).
    """
    del working_dir
    root = Path(sim_dir)
    if not root.is_dir():
        return {"success": False, "error": f"sim_dir not found: {sim_dir}"}

    rep_dirs = discover_analysis_rep_dirs(root)
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
        metric_filenames = _discover_metric_names(rep_dirs)
    else:
        discovered = set(_discover_metric_names(rep_dirs))
        metric_filenames = sorted(set(metric_filenames) | discovered)

    avg = analysis_avg_dir(root)
    avg.mkdir(parents=True, exist_ok=True)
    _cleanup_avg_junk(avg)
    scalars: Dict[str, Any] = {"n_reps": len(rep_dirs), "reps": [d.name for d in rep_dirs]}
    written: List[str] = []
    errors: List[str] = []
    skipped: List[str] = []

    for name in metric_filenames:
        if name.lower() in SKIP_BASENAMES:
            skipped.append(name)
            continue
        paths = []
        for d in rep_dirs:
            hit = _find_metric_in_dir(d, name)
            if hit:
                paths.append((d.name, hit))
        if len(paths) < 2:
            errors.append(f"{name}: found in {len(paths)} reps")
            continue
        try:
            w, sc = _dispatch_aggregate(name, paths, avg)
            if sc.get("skipped"):
                skipped.append(name)
                continue
            written.extend(w)
            scalars[Path(name).stem] = sc
        except Exception as exc:
            errors.append(f"{name}: {exc}")
            logger.warning("aggregate_replicate_metrics failed for %s: %s", name, exc)

    # Final junk sweep (fel_* leftovers if fel_grid was skipped)
    _cleanup_avg_junk(avg)

    summary_path = avg / "summary_scalars.json"
    summary_path.write_text(
        json.dumps({**scalars, "skipped": skipped, "errors": errors}, indent=2) + "\n",
        encoding="utf-8",
    )
    written.append(str(summary_path))

    return {
        "success": bool(written) and (
            any(Path(name).stem in scalars for name in metric_filenames)
            or len(written) > 1
        ),
        "avg_dir": str(avg),
        "n_reps": len(rep_dirs),
        "written": written,
        "errors": errors,
        "skipped": skipped,
        "scalars": scalars,
    }
