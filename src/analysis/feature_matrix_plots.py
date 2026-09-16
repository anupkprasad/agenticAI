"""Plot helpers for (frames × features) arrays and PCA projections.

Used by modular consensus tools and ``analysis/avg`` aggregation so tall
matrices are not drawn with ``aspect='equal'`` (which shrinks them into a
thin strip with huge whitespace).

Dihedral-related matrices (``*_deg``, ``*sincos*``) are drawn as trajectory
line plots (mean ± std across residues/features vs frame).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

import numpy as np

logger = logging.getLogger(__name__)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except Exception:
    HAS_MPL = False


PathLike = Union[str, Path]


def _infer_kind(stem: str, shape: tuple) -> str:
    low = stem.lower()
    if "projection" in low:
        return "projections"
    if low.endswith("_deg") or low in {"phi_deg", "psi_deg", "chi1_deg"}:
        return "angle_deg"
    if "sincos" in low:
        return "sincos"
    if "dccm" in low:
        return "correlation"
    nr, nc = int(shape[0]), int(shape[1]) if len(shape) > 1 else 1
    if nc <= 4 and nr >= 10:
        return "projections" if nc == 2 else "time_series_cols"
    if nr >= 2 * nc and nr > 50:
        return "time_feature"
    if abs(nr - nc) <= max(2, int(0.05 * max(nr, nc))):
        return "correlation"
    return "time_feature"


def _circ_mean_std_over_features(deg: np.ndarray) -> tuple:
    """Per-frame circular mean ± circular std across columns (residues)."""
    rad = np.deg2rad(np.asarray(deg, dtype=float))
    cos_m = np.nanmean(np.cos(rad), axis=1)
    sin_m = np.nanmean(np.sin(rad), axis=1)
    mean = np.rad2deg(np.arctan2(sin_m, cos_m))
    r = np.clip(np.sqrt(cos_m * cos_m + sin_m * sin_m), 1e-12, 1.0)
    std = np.rad2deg(np.sqrt(np.maximum(0.0, -2.0 * np.log(r))))
    return mean, std


def _linear_mean_std_over_features(
    mat: np.ndarray,
    std_mat: Optional[np.ndarray] = None,
) -> tuple:
    """Per-frame mean ± std across columns; prefer column-mean of ``std_mat`` when given."""
    arr = np.asarray(mat, dtype=float)
    mean = np.nanmean(arr, axis=1)
    if std_mat is not None and np.asarray(std_mat).shape == arr.shape:
        std = np.nanmean(np.asarray(std_mat, dtype=float), axis=1)
    else:
        std = np.nanstd(arr, axis=1)
    std = np.where(np.isfinite(std), std, 0.0)
    return mean, std


def _save_mean_std_trajectory_png(
    mat: np.ndarray,
    output_path: Path,
    *,
    title: str,
    ylabel: str,
    circular: bool = False,
    std_mat: Optional[np.ndarray] = None,
    dpi: int = 150,
) -> Optional[str]:
    """Line plot: per-frame feature mean ± std vs frame index."""
    if not HAS_MPL:
        return None
    arr = np.asarray(mat, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2:
        return None
    if circular:
        y, s = _circ_mean_std_over_features(arr)
        if std_mat is not None and np.asarray(std_mat).shape == arr.shape:
            s_rep = np.nanmean(np.asarray(std_mat, dtype=float), axis=1)
            s_rep = np.where(np.isfinite(s_rep), s_rep, 0.0)
            s = np.maximum(s, s_rep)
    else:
        y, s = _linear_mean_std_over_features(arr, std_mat=std_mat)

    x = np.arange(arr.shape[0], dtype=float)
    fig, ax = plt.subplots(figsize=(8.5, 4.2))
    ax.plot(x, y, color="C0", linewidth=1.4, label="mean")
    ax.fill_between(x, y - s, y + s, color="C0", alpha=0.25, linewidth=0, label="± std")
    ax.set_xlabel("Frame")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if circular:
        finite = y[np.isfinite(y)]
        if finite.size:
            lo = float(np.nanmin(y - s))
            hi = float(np.nanmax(y + s))
            pad = max(5.0, 0.05 * (hi - lo + 1e-6))
            ax.set_ylim(max(-180.0, lo - pad), min(180.0, hi + pad))
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, alpha=0.25, linestyle="--")
    fig.tight_layout()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return str(output_path)


def save_feature_matrix_png(
    mat: np.ndarray,
    output_path: PathLike,
    *,
    title: Optional[str] = None,
    kind: Optional[str] = None,
    std_mat: Optional[np.ndarray] = None,
    dpi: int = 150,
) -> Optional[str]:
    """Write a PNG for a 2D feature matrix; return path or None if skipped.

    Dihedral angle / sincos matrices use trajectory mean±std line plots.
    Pass ``std_mat`` (same shape) when replicate std is available under avg/.
    """
    if not HAS_MPL:
        return None
    arr = np.asarray(mat, dtype=float)
    if arr.ndim != 2 or arr.size == 0:
        return None
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    stem = out.stem.replace("_mean", "").replace("_overlay", "")
    plot_kind = kind or _infer_kind(stem, arr.shape)
    ttl = title or stem

    try:
        if plot_kind == "angle_deg":
            return _save_mean_std_trajectory_png(
                arr,
                out,
                title=ttl,
                ylabel="Angle (°)",
                circular=True,
                std_mat=std_mat,
                dpi=dpi,
            )
        if plot_kind == "sincos":
            return _save_mean_std_trajectory_png(
                arr,
                out,
                title=ttl,
                ylabel="sin/cos feature mean",
                circular=False,
                std_mat=std_mat,
                dpi=dpi,
            )

        if plot_kind == "projections":
            fig, ax = plt.subplots(figsize=(6.5, 5.5))
            x = arr[:, 0]
            y = arr[:, 1] if arr.shape[1] > 1 else np.arange(arr.shape[0])
            t = np.arange(arr.shape[0])
            sc = ax.scatter(x, y, c=t, s=6, cmap="viridis", alpha=0.75, linewidths=0)
            fig.colorbar(sc, ax=ax, label="Frame")
            ax.set_xlabel("PC1" if "tica" not in stem.lower() else "IC1")
            ax.set_ylabel("PC2" if arr.shape[1] > 1 else "index")
            ax.set_title(ttl)
            ax.grid(True, alpha=0.25, linestyle="--")
            fig.tight_layout()
            fig.savefig(out, dpi=dpi, bbox_inches="tight")
            plt.close(fig)
            return str(out)

        if plot_kind == "time_series_cols":
            fig, ax = plt.subplots(figsize=(8, 4.5))
            for j in range(arr.shape[1]):
                ax.plot(arr[:, j], linewidth=1.0, alpha=0.85, label=f"col{j+1}")
            ax.set_xlabel("Frame")
            ax.set_ylabel("Value")
            ax.set_title(ttl)
            if arr.shape[1] <= 6:
                ax.legend(fontsize=8, loc="best")
            ax.grid(True, alpha=0.25, linestyle="--")
            fig.tight_layout()
            fig.savefig(out, dpi=dpi, bbox_inches="tight")
            plt.close(fig)
            return str(out)

        # Heatmaps for correlation / generic matrices.
        fig_w = 7.5 if arr.shape[1] >= 20 else 6.0
        fig_h = 5.5 if arr.shape[0] >= 200 else 4.5
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))
        if plot_kind == "correlation":
            lim = float(np.nanmax(np.abs(arr))) if np.isfinite(arr).any() else 1.0
            lim = max(lim, 1e-6)
            vmax = 1.0 if lim <= 1.05 else lim
            im = ax.imshow(
                arr,
                cmap="coolwarm",
                vmin=-vmax,
                vmax=vmax,
                origin="lower",
                aspect="equal",
                interpolation="nearest",
            )
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            ax.set_xlabel("Index")
            ax.set_ylabel("Index")
        else:  # time_feature
            finite = arr[np.isfinite(arr)]
            if finite.size:
                lo, hi = float(np.percentile(finite, 2)), float(np.percentile(finite, 98))
                if abs(hi - lo) < 1e-12:
                    lo, hi = float(np.nanmin(finite)), float(np.nanmax(finite))
            else:
                lo, hi = -1.0, 1.0
            im = ax.imshow(
                arr,
                cmap="viridis",
                vmin=lo,
                vmax=hi,
                origin="lower",
                aspect="auto",
                interpolation="nearest",
            )
            fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
            ax.set_xlabel("Feature index")
            ax.set_ylabel("Frame")
        ax.set_title(ttl)
        fig.tight_layout()
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        return str(out)
    except Exception:
        logger.exception("save_feature_matrix_png failed for %s", out)
        try:
            plt.close("all")
        except Exception:
            pass
        return None


def save_rmsf_profile_png(
    csv_path: PathLike,
    output_path: PathLike,
    *,
    title: str = "Consensus Cα RMSF",
    dpi: int = 150,
) -> Optional[str]:
    """Bar/line plot from ``per_residue_rmsf.csv`` (resid, rmsf_A)."""
    if not HAS_MPL:
        return None
    path = Path(csv_path)
    if not path.is_file():
        return None
    resids: list = []
    vals: list = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        fh.readline()
        for line in fh:
            parts = line.strip().split(",")
            if len(parts) < 4:
                continue
            try:
                resids.append(int(float(parts[1])))
                vals.append(float(parts[3]))
            except ValueError:
                continue
    if not vals:
        return None
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.bar(resids, vals, width=1.0, color="C0", alpha=0.85)
    ax.set_xlabel("Residue")
    ax.set_ylabel("RMSF (Å)")
    ax.set_title(title)
    ax.grid(True, axis="y", alpha=0.25, linestyle="--")
    fig.tight_layout()
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return str(out)


def save_dihedral_summary_png(
    csv_path: PathLike,
    output_path: PathLike,
    *,
    title: str = "Per-residue dihedral circular means",
    dpi: int = 150,
) -> Optional[str]:
    """Plot φ/ψ/χ₁ circular means from ``per_residue_dihedrals.csv``."""
    if not HAS_MPL:
        return None
    path = Path(csv_path)
    if not path.is_file():
        return None
    resids: list = []
    phi: list = []
    psi: list = []
    chi: list = []
    with path.open("r", encoding="utf-8", errors="ignore") as fh:
        fh.readline()
        for line in fh:
            parts = [p.strip() for p in line.strip().split(",")]
            if len(parts) < 11:
                continue
            try:
                resids.append(int(float(parts[2])))
                phi.append(float(parts[5]) if parts[5] else np.nan)
                psi.append(float(parts[7]) if parts[7] else np.nan)
                chi.append(float(parts[9]) if parts[9] else np.nan)
            except ValueError:
                continue
    if not resids:
        return None
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.plot(resids, phi, ".", markersize=4, label="φ mean")
    ax.plot(resids, psi, ".", markersize=4, label="ψ mean")
    ax.plot(resids, chi, ".", markersize=4, label="χ₁ mean")
    ax.set_xlabel("Residue")
    ax.set_ylabel("Circular mean (°)")
    ax.set_ylim(-180, 180)
    ax.set_title(title)
    ax.legend(fontsize=8, loc="best")
    ax.grid(True, alpha=0.25, linestyle="--")
    fig.tight_layout()
    fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return str(out)
