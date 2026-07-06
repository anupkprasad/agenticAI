"""
Unsupervised clustering on classification feature matrices.

Reads ``classification_features_zscore.csv`` (recommended) or raw CSV,
runs hierarchical (default) or k-means clustering, and writes assignments
plus plots labeled with protein / simulation names.
"""
from __future__ import annotations

import csv
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from langchain.tools import tool
from scipy.cluster import hierarchy, vq

logger = logging.getLogger(__name__)

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except ImportError:
    HAS_MPL = False
    plt = None  # type: ignore

from src.reporter.combined_reporter import _parse_label_name_map, resolve_display_label

_META_COLUMNS = frozenset({"label", "sim_directory", "n_features_present"})


def _default_n_clusters(n_samples: int) -> int:
    """Heuristic cluster count when the user does not specify one."""
    if n_samples <= 2:
        return max(1, n_samples)
    return max(2, min(8, int(round(np.sqrt(n_samples)))))


def _parse_n_clusters_from_text(text: str) -> Optional[int]:
    if not text:
        return None
    m = re.search(r"\b(\d{1,2})\s+clusters?\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"\bcluster(?:ing)?\s+(?:into|with|using)\s+(\d{1,2})\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def clustering_method_for_goal(*goal_texts: str) -> str:
    """Return ``kmeans`` when explicitly requested; otherwise ``hierarchical``."""
    for text in goal_texts:
        if not text:
            continue
        normalized = text.lower().replace("\u2011", "-")
        if re.search(r"\bk[-\s]?means?\b", normalized):
            return "kmeans"
    return "hierarchical"


def _label_base(label: str) -> str:
    """Strip common suffixes (``.pdb``) for name-map lookup."""
    low = label.lower()
    if low.endswith(".pdb"):
        return label[:-4]
    return label


def _load_feature_matrix(
    csv_path: Path,
    min_features_present: int = 1,
) -> Tuple[List[str], List[str], List[str], np.ndarray, List[str]]:
    """
    Load feature matrix from classification CSV.

    Returns (labels, display_names, sim_dirs, X, feature_columns).
    Rows with fewer than ``min_features_present`` non-NaN features are dropped.
    Rows are sorted by label for reproducible clustering order.
    """
    with open(csv_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise ValueError(f"No columns in {csv_path}")
        feature_cols = [c for c in reader.fieldnames if c not in _META_COLUMNS]

        labels: List[str] = []
        display_names: List[str] = []
        sim_dirs: List[str] = []
        rows: List[List[float]] = []

        for row in reader:
            label = (row.get("label") or "").strip()
            if not label:
                continue
            vals: List[float] = []
            present = 0
            for col in feature_cols:
                raw = (row.get(col) or "").strip()
                if raw == "":
                    vals.append(np.nan)
                else:
                    try:
                        vals.append(float(raw))
                        present += 1
                    except ValueError:
                        vals.append(np.nan)
            if present < min_features_present:
                logger.warning(
                    "Skipping %s: only %d/%d features present",
                    label,
                    present,
                    len(feature_cols),
                )
                continue
            labels.append(label)
            display_names.append(label)
            sim_dirs.append((row.get("sim_directory") or "").strip())
            rows.append(vals)

    if not rows:
        raise ValueError(
            f"No usable rows in {csv_path} (need ≥{min_features_present} features per sim)"
        )

    order = sorted(range(len(labels)), key=lambda i: labels[i].lower())
    labels = [labels[i] for i in order]
    display_names = [display_names[i] for i in order]
    sim_dirs = [sim_dirs[i] for i in order]
    rows = [rows[i] for i in order]

    return labels, display_names, sim_dirs, np.array(rows, dtype=float), feature_cols


def _filter_usable_feature_columns(
    X: np.ndarray,
    feature_cols: Sequence[str],
    max_missing_fraction: float = 0.25,
) -> Tuple[np.ndarray, List[str], List[str]]:
    """
    Drop feature columns that are mostly missing or have <2 observed values.

    Returns (filtered_X, kept_columns, dropped_columns).
    """
    keep_indices: List[int] = []
    dropped: List[str] = []
    n_rows = X.shape[0]
    for j, col in enumerate(feature_cols):
        col_vals = X[:, j]
        n_missing = int(np.isnan(col_vals).sum())
        n_present = n_rows - n_missing
        if n_present < 2:
            dropped.append(col)
            continue
        if n_missing / n_rows > max_missing_fraction:
            dropped.append(col)
            continue
        keep_indices.append(j)

    if not keep_indices:
        raise ValueError(
            "No usable feature columns remain after missing-data filtering "
            f"(max_missing_fraction={max_missing_fraction})"
        )

    kept = [feature_cols[j] for j in keep_indices]
    return X[:, keep_indices], kept, dropped


def _impute_column_means(X: np.ndarray) -> Tuple[np.ndarray, Dict[str, int]]:
    """Replace NaN with column mean; all-NaN columns become zeros."""
    out = X.copy()
    imputed_cells = 0
    for j in range(out.shape[1]):
        col = out[:, j]
        mask = np.isnan(col)
        if not mask.any():
            continue
        mean = np.nanmean(col)
        if np.isnan(mean):
            out[:, j] = 0.0
            imputed_cells += int(mask.sum())
        else:
            col[mask] = mean
            out[:, j] = col
            imputed_cells += int(mask.sum())
    return out, {"imputed_cells": imputed_cells, "total_cells": out.size}


def _pca_2d(X: np.ndarray) -> Tuple[np.ndarray, float, float]:
    """First two principal components (SVD). Returns coords, var PC1, var PC2."""
    Xc = X - X.mean(axis=0)
    if Xc.shape[0] < 2 or Xc.shape[1] < 1:
        return np.zeros((X.shape[0], 2)), 0.0, 0.0
    _, s, vt = np.linalg.svd(Xc, full_matrices=False)
    coords = Xc @ vt[:2].T
    n = max(X.shape[0] - 1, 1)
    var = (s ** 2) / n
    total = float(var.sum()) or 1.0
    pc1_var = float(var[0] / total) if len(var) > 0 else 0.0
    pc2_var = float(var[1] / total) if len(var) > 1 else 0.0
    return coords, pc1_var, pc2_var


def _cluster_hierarchical(
    X: np.ndarray,
    n_clusters: int,
    linkage_method: str = "ward",
) -> Tuple[np.ndarray, np.ndarray]:
    Z = hierarchy.linkage(X, method=linkage_method)
    labels = hierarchy.fcluster(Z, t=n_clusters, criterion="maxclust")
    return labels.astype(int), Z


def _cluster_kmeans(X: np.ndarray, n_clusters: int, seed: int = 42) -> np.ndarray:
    rng = np.random.default_rng(seed)
    if X.shape[0] <= n_clusters:
        return np.arange(1, X.shape[0] + 1, dtype=int)
    _, labels = vq.kmeans2(
        X,
        n_clusters,
        minit="++",
        seed=rng,
    )
    return labels.astype(int) + 1


def _apply_display_names(
    labels: Sequence[str],
    user_goal: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
) -> List[str]:
    name_map: Dict[str, str] = dict(label_name_map or {})
    parsed = _parse_label_name_map(user_goal)
    for key, val in parsed.items():
        name_map.setdefault(key.lower(), val)
    out: List[str] = []
    for label in labels:
        base = _label_base(label)
        resolved = resolve_display_label(base, name_map)
        out.append(resolved)
    return out


def _plot_cluster_scatter(
    coords: np.ndarray,
    display_names: Sequence[str],
    cluster_ids: Sequence[int],
    output_path: Path,
    title: str,
    pc1_var: float,
    pc2_var: float,
) -> None:
    if not HAS_MPL:
        return
    fig, ax = plt.subplots(figsize=(10, 8))
    clusters = sorted(set(cluster_ids))
    cmap = plt.cm.get_cmap("tab10", max(len(clusters), 1))
    for i, cid in enumerate(clusters):
        mask = np.array(cluster_ids) == cid
        ax.scatter(
            coords[mask, 0],
            coords[mask, 1],
            s=120,
            c=[cmap(i)],
            label=f"Cluster {cid}",
            edgecolors="black",
            linewidths=0.6,
            zorder=2,
        )
    for idx, name in enumerate(display_names):
        ax.annotate(
            name,
            (coords[idx, 0], coords[idx, 1]),
            textcoords="offset points",
            xytext=(6, 6),
            fontsize=9,
            fontweight="bold",
            zorder=3,
        )
    ax.set_xlabel(f"PC1 ({pc1_var * 100:.1f}% var)")
    ax.set_ylabel(f"PC2 ({pc2_var * 100:.1f}% var)")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _plot_dendrogram(
    linkage_matrix: np.ndarray,
    display_names: Sequence[str],
    output_path: Path,
    title: str,
) -> None:
    if not HAS_MPL:
        return
    fig, ax = plt.subplots(figsize=(max(8, len(display_names) * 0.55), 6))
    hierarchy.dendrogram(
        linkage_matrix,
        labels=list(display_names),
        leaf_rotation=45,
        leaf_font_size=9,
        ax=ax,
    )
    ax.set_title(title)
    ax.set_ylabel("Distance")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _cluster_color_map(cluster_ids: Sequence[int]):
    """Return sorted cluster ids and a color for each."""
    clusters = sorted(set(cluster_ids))
    cmap = plt.cm.get_cmap("tab10", max(len(clusters), 1))
    colors = {cid: cmap(i) for i, cid in enumerate(clusters)}
    return clusters, colors


def _tree_leaf_count(node) -> int:
    if node.is_leaf():
        return 1
    return _tree_leaf_count(node.get_left()) + _tree_leaf_count(node.get_right())


def _assign_circular_angles(node, start: float, span: float, angles: Dict[int, float]) -> None:
    """Assign polar angles proportional to subtree leaf counts."""
    if node.is_leaf():
        angles[node.id] = start + span / 2.0
        return
    left = node.get_left()
    right = node.get_right()
    left_count = _tree_leaf_count(left)
    right_count = _tree_leaf_count(right)
    total = left_count + right_count
    left_span = span * left_count / total if total else span / 2.0
    _assign_circular_angles(left, start, left_span, angles)
    _assign_circular_angles(right, start + left_span, span - left_span, angles)
    angles[node.id] = start + span / 2.0


def _assign_radial_depths(node, radius: float, radii: Dict[int, float]) -> None:
    """Assign radial depth from the tree root (center) using branch lengths."""
    radii[node.id] = radius
    if node.is_leaf():
        return
    _assign_radial_depths(node.get_left(), radius + node.get_left().dist, radii)
    _assign_radial_depths(node.get_right(), radius + node.get_right().dist, radii)


def _polar_to_xy(theta: float, radius: float) -> Tuple[float, float]:
    return radius * np.cos(theta), radius * np.sin(theta)


def _plot_unrooted_phylo_tree(
    linkage_matrix: np.ndarray,
    display_names: Sequence[str],
    cluster_ids: Sequence[int],
    output_path: Path,
    title: str,
) -> None:
    """
    Circular unrooted phylogram from a scipy linkage matrix.

    Leaf tips and terminal branches are colored by cluster assignment.
    """
    if not HAS_MPL:
        return

    n_samples = len(display_names)
    if n_samples < 2:
        return

    root = hierarchy.to_tree(linkage_matrix, rd=False)
    angles: Dict[int, float] = {}
    radii: Dict[int, float] = {}
    _assign_circular_angles(root, 0.0, 2.0 * np.pi, angles)
    _assign_radial_depths(root, 0.0, radii)
    max_radius = max(radii.values()) or 1.0
    label_radius = max_radius * 1.1

    clusters, cluster_colors = _cluster_color_map(cluster_ids)
    leaf_cluster = {idx: int(cluster_ids[idx]) for idx in range(n_samples)}

    fig_size = max(8.0, min(14.0, 6.0 + n_samples * 0.35))
    fig, ax = plt.subplots(figsize=(fig_size, fig_size))
    ax.set_aspect("equal")

    def _draw_edges(node) -> None:
        if node.is_leaf():
            return
        parent_angle = angles[node.id]
        parent_radius = radii[node.id]
        parent_x, parent_y = _polar_to_xy(parent_angle, parent_radius)
        for child in (node.get_left(), node.get_right()):
            child_angle = angles[child.id]
            child_radius = radii[child.id]
            child_x, child_y = _polar_to_xy(child_angle, child_radius)
            junction_x, junction_y = _polar_to_xy(child_angle, parent_radius)
            if child.is_leaf():
                color = cluster_colors[leaf_cluster[child.id]]
                lw = 2.0
            else:
                color = "#666666"
                lw = 1.3
            ax.plot(
                [child_x, junction_x, parent_x],
                [child_y, junction_y, parent_y],
                color=color,
                linewidth=lw,
                solid_capstyle="round",
                zorder=1,
            )
            _draw_edges(child)

    _draw_edges(root)

    for idx, name in enumerate(display_names):
        cid = leaf_cluster[idx]
        color = cluster_colors[cid]
        theta = angles[idx]
        tip_x, tip_y = _polar_to_xy(theta, radii[idx])
        ax.scatter(
            [tip_x],
            [tip_y],
            s=140,
            c=[color],
            edgecolors="black",
            linewidths=0.7,
            zorder=3,
        )
        label_x, label_y = _polar_to_xy(theta, label_radius)
        ha = "left" if np.cos(theta) >= 0 else "right"
        ax.text(
            label_x,
            label_y,
            name,
            ha=ha,
            va="center",
            fontsize=9,
            fontweight="bold",
            color=color,
            zorder=4,
        )

    for cid in clusters:
        ax.scatter(
            [],
            [],
            c=[cluster_colors[cid]],
            s=80,
            edgecolors="black",
            linewidths=0.6,
            label=f"Cluster {cid}",
        )
    ax.legend(loc="upper right", fontsize=9, framealpha=0.9)
    ax.set_title(title)
    margin = max_radius * 0.28
    ax.set_xlim(-max_radius - margin, max_radius + margin)
    ax.set_ylim(-max_radius - margin, max_radius + margin)
    ax.axis("off")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


@tool
def cluster_classification_features(
    working_dir: str = "",
    features_file: str = "classification_features_zscore.csv",
    method: str = "hierarchical",
    n_clusters: Optional[int] = None,
    linkage_method: str = "ward",
    user_goal: str = "",
    label_name_map: Optional[Dict[str, str]] = None,
    min_features_present: int = 1,
    max_column_missing_fraction: float = 0.25,
    assignments_file: str = "classification_cluster_assignments.csv",
    scatter_plot_file: str = "classification_clusters_pca.png",
    dendrogram_file: str = "classification_dendrogram.png",
    phylo_tree_file: str = "classification_phylo_tree.png",
    summary_file: str = "classification_clusters.json",
) -> Dict[str, Any]:
    """
    Cluster simulations from a classification feature table (z-score CSV recommended).

    Default method is hierarchical agglomerative clustering (Ward linkage).
    Use method='kmeans' for k-means. Writes cluster assignments and a PCA scatter
    plot with protein/simulation name labels; hierarchical runs also get a dendrogram
    and an unrooted circular phylogenetic tree colored by cluster.

    Args:
        working_dir: Directory containing the features CSV (usually base/analysis).
        features_file: Input CSV (prefer classification_features_zscore.csv).
        method: 'hierarchical' (default) or 'kmeans'.
        n_clusters: Number of clusters; auto-chosen from sample size if omitted.
        linkage_method: scipy linkage for hierarchical ('ward', 'average', 'complete').
        user_goal: Optional goal text to parse id:name labels (e.g. p23458:JAK1).
        label_name_map: Optional explicit {uniprot_id: protein_name} map (preferred).
        min_features_present: Skip sims with fewer non-NaN feature values.
        max_column_missing_fraction: Drop feature columns missing in more than
            this fraction of simulations (default 0.25) before clustering.
        assignments_file: Output CSV with label, display_name, cluster_id.
        scatter_plot_file: PCA scatter colored by cluster with name annotations.
        dendrogram_file: Dendrogram PNG (hierarchical only).
        phylo_tree_file: Unrooted circular phylogram PNG colored by cluster (hierarchical only).
        summary_file: JSON summary of clustering parameters and results.
    """
    original_dir = os.getcwd()
    try:
        feat_path = Path(features_file)
        if not feat_path.is_absolute():
            base = Path(working_dir) if working_dir else Path(".")
            feat_path = (base / features_file).resolve()
        if not feat_path.is_file():
            return {"success": False, "error": f"Features file not found: {feat_path}"}

        method_norm = (method or "hierarchical").lower().replace("-", "").replace("_", "")
        if method_norm in ("kmeans", "kmean"):
            method_key = "kmeans"
        elif method_norm in ("hierarchical", "hier", "agglomerative"):
            method_key = "hierarchical"
        else:
            return {
                "success": False,
                "error": f"Unknown method {method!r}; use 'hierarchical' or 'kmeans'",
            }

        labels, _, sim_dirs, X_raw, feature_cols = _load_feature_matrix(
            feat_path, min_features_present=min_features_present
        )
        X_filtered, feature_cols, dropped_cols = _filter_usable_feature_columns(
            X_raw,
            feature_cols,
            max_missing_fraction=max_column_missing_fraction,
        )
        if dropped_cols:
            logger.warning(
                "Dropped %d feature column(s) with excessive missing data: %s",
                len(dropped_cols),
                ", ".join(dropped_cols),
            )

        display_names = _apply_display_names(
            labels, user_goal=user_goal, label_name_map=label_name_map
        )
        n_samples = X_filtered.shape[0]
        k = n_clusters or _parse_n_clusters_from_text(user_goal) or _default_n_clusters(n_samples)
        k = max(1, min(k, n_samples))

        X, impute_stats = _impute_column_means(X_filtered)
        coords, pc1_var, pc2_var = _pca_2d(X)

        linkage_matrix = None
        if method_key == "hierarchical":
            cluster_ids, linkage_matrix = _cluster_hierarchical(
                X, k, linkage_method=linkage_method
            )
        else:
            cluster_ids = _cluster_kmeans(X, k)

        out_dir = feat_path.parent
        assign_path = out_dir / assignments_file
        with open(assign_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(
                fh,
                fieldnames=["label", "display_name", "sim_directory", "cluster_id", "method"],
            )
            writer.writeheader()
            for i, label in enumerate(labels):
                writer.writerow(
                    {
                        "label": label,
                        "display_name": display_names[i],
                        "sim_directory": sim_dirs[i],
                        "cluster_id": int(cluster_ids[i]),
                        "method": method_key,
                    }
                )

        scatter_path = out_dir / scatter_plot_file
        method_title = "Hierarchical" if method_key == "hierarchical" else "K-means"
        if HAS_MPL:
            _plot_cluster_scatter(
                coords,
                display_names,
                cluster_ids,
                scatter_path,
                title=f"{method_title} clustering (k={k}) — z-score features",
                pc1_var=pc1_var,
                pc2_var=pc2_var,
            )
        else:
            scatter_path = None

        dendro_path = None
        phylo_path = None
        if method_key == "hierarchical" and linkage_matrix is not None and HAS_MPL:
            dendro_path = out_dir / dendrogram_file
            _plot_dendrogram(
                linkage_matrix,
                display_names,
                dendro_path,
                title=f"Hierarchical clustering dendrogram (k={k})",
            )
            phylo_path = out_dir / phylo_tree_file
            _plot_unrooted_phylo_tree(
                linkage_matrix,
                display_names,
                cluster_ids,
                phylo_path,
                title=f"Unrooted phylogenetic tree (k={k}) — z-score features",
            )

        summary = {
            "method": method_key,
            "n_clusters": k,
            "n_simulations": n_samples,
            "feature_columns": feature_cols,
            "dropped_feature_columns": dropped_cols,
            "imputation": impute_stats,
            "row_order": labels,
            "reproducibility_note": (
                "Hierarchical Ward clustering is deterministic for a fixed z-score "
                "matrix. Re-runs differ when the feature table changes (metric "
                "groups, missing per-sim outputs, or re-computed analysis values)."
            ),
            "features_file": str(feat_path),
            "assignments_file": str(assign_path),
            "scatter_plot": str(scatter_path) if scatter_path else None,
            "dendrogram_plot": str(dendro_path) if dendro_path else None,
            "phylo_tree_plot": str(phylo_path) if phylo_path else None,
            "linkage_method": linkage_method if method_key == "hierarchical" else None,
            "labels": labels,
            "display_names": display_names,
            "cluster_assignments": {
                labels[i]: int(cluster_ids[i]) for i in range(len(labels))
            },
        }
        summary_path = out_dir / summary_file
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

        plot_note = ""
        if not HAS_MPL:
            plot_note = " (matplotlib unavailable — plots skipped)"

        return {
            "success": True,
            "message": (
                f"{method_title} clustering: {n_samples} simulations → {k} clusters"
                f"{plot_note}"
            ),
            "method": method_key,
            "n_clusters": k,
            "assignments_file": str(assign_path),
            "scatter_plot": str(scatter_path) if scatter_path else None,
            "dendrogram_plot": str(dendro_path) if dendro_path else None,
            "phylo_tree_plot": str(phylo_path) if phylo_path else None,
            "summary_file": str(summary_path),
            "cluster_assignments": summary["cluster_assignments"],
            "display_names": display_names,
            "feature_columns": feature_cols,
            "dropped_feature_columns": dropped_cols,
            "imputation": impute_stats,
        }
    except Exception as exc:
        logger.exception("cluster_classification_features failed")
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)


# Trajectory metrics that have per-frame time series (not per-residue scalars).
CLUSTER_TRAJECTORY_METRIC_GROUPS: Tuple[str, ...] = (
    "com",
    "contacts",
    "pocket_sasa",
    "residence",
)

_CLUSTER_TRAJECTORY_CONFIG: Dict[str, Dict[str, Any]] = {
    "com": {
        "title": "Ligand–Pocket COM Distance",
        "ylabel": "COM Distance (Å)",
        "output_file": "com_distance_by_cluster.png",
        "x_col": 1,
        "y_col": 2,
    },
    "contacts": {
        "title": "Protein–Ligand Contacts",
        "ylabel": "Heavy-Atom Contacts",
        "output_file": "contacts_by_cluster.png",
        "file_pattern": "protein_ligand_contacts",
        "x_col": 1,
        "y_col": 3,
    },
    "pocket_sasa": {
        "title": "Pocket SASA",
        "ylabel": "Pocket SASA (nm²)",
        "output_file": "pocket_sasa_by_cluster.png",
        "file_pattern": "pocket_sasa",
        "x_col": 0,
        "y_col": 1,
    },
    "residence": {
        "title": "Ligand Bound State",
        "ylabel": "Bound (0/1)",
        "output_file": "ligand_residence_by_cluster.png",
        "file_pattern": "ligand_residence",
        "x_col": 0,
        "y_col": 1,
    },
}


def _load_cluster_assignments(
    assignments_path: Path,
) -> Tuple[Dict[int, List[Dict[str, str]]], List[int]]:
    """Group assignment rows by cluster_id."""
    by_cluster: Dict[int, List[Dict[str, str]]] = {}
    with open(assignments_path, newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            cid = int(row["cluster_id"])
            by_cluster.setdefault(cid, []).append(
                {
                    "label": row.get("label", ""),
                    "display_name": row.get("display_name") or row.get("label", ""),
                    "sim_directory": row.get("sim_directory", ""),
                }
            )
    cluster_ids = sorted(by_cluster)
    return by_cluster, cluster_ids


def _find_trajectory_file(sim_directory: str, metric_group: str) -> Optional[str]:
    """Locate a time-series CSV/dat for one simulation and metric group."""
    from src.analysis.combined_analysis import (
        _find_com_distance_file,
        _find_metric_file,
    )

    sim_path = Path(sim_directory)
    search_roots = [
        sim_path / "analysis",
        sim_path,
    ]
    if metric_group == "com":
        for root in search_roots:
            if root.is_dir():
                hit = _find_com_distance_file(str(root))
                if hit:
                    return hit
        return None

    cfg = _CLUSTER_TRAJECTORY_CONFIG.get(metric_group, {})
    pattern = cfg.get("file_pattern", metric_group)
    for root in search_roots:
        if root.is_dir():
            hit = _find_metric_file(str(root), pattern)
            if hit:
                return hit
    return None


def _plot_metric_by_cluster_panels(
    by_cluster: Dict[int, List[Dict[str, str]]],
    cluster_ids: Sequence[int],
    metric_group: str,
    output_path: Path,
    n_clusters_total: int,
    figsize_per_panel: Tuple[float, float] = (10.0, 3.0),
    dpi: int = 150,
) -> bool:
    """Draw one subplot per cluster with trajectories for sims in that cluster."""
    if not HAS_MPL:
        return False

    from src.analysis.combined_analysis import _read_two_column_file

    cfg = _CLUSTER_TRAJECTORY_CONFIG[metric_group]
    x_col = int(cfg["x_col"])
    y_col = int(cfg["y_col"])

    all_names = sorted(
        {
            row["display_name"]
            for members in by_cluster.values()
            for row in members
        }
    )
    cmap = plt.cm.get_cmap("tab10", max(len(all_names), 1))
    name_colors = {name: cmap(i) for i, name in enumerate(all_names)}

    n_panels = len(cluster_ids)
    fig, axes = plt.subplots(
        n_panels,
        1,
        figsize=(figsize_per_panel[0], figsize_per_panel[1] * n_panels),
        squeeze=False,
    )

    any_data = False
    for idx, cid in enumerate(cluster_ids):
        ax = axes[idx, 0]
        members = by_cluster.get(cid, [])
        plotted = 0
        for row in members:
            sim_dir = row.get("sim_directory") or ""
            display_name = row.get("display_name") or row.get("label", "")
            if not sim_dir:
                continue
            fpath = _find_trajectory_file(sim_dir, metric_group)
            if not fpath:
                logger.warning(
                    "No trajectory file for %s (%s)", display_name, metric_group
                )
                continue
            try:
                xs, ys = _read_two_column_file(fpath, x_col=x_col, y_col=y_col)
                color = name_colors.get(display_name, "#333333")
                ax.plot(xs, ys, label=display_name, color=color, linewidth=1.1, alpha=0.88)
                plotted += 1
                any_data = True
            except Exception as exc:
                logger.warning(
                    "Skipping %s trajectory (%s): %s", display_name, fpath, exc
                )

        ax.set_ylabel(cfg["ylabel"], fontsize=9)
        ax.set_title(
            f"Cluster {cid} (n={len(members)}) — {cfg['title']}",
            fontsize=10,
            fontweight="bold",
        )
        ax.grid(True, alpha=0.3)
        if plotted:
            ax.legend(loc="best", fontsize=8, ncol=min(plotted, 3))
        else:
            ax.text(
                0.5,
                0.5,
                "No trajectory data",
                transform=ax.transAxes,
                ha="center",
                va="center",
                fontsize=10,
                color="#666666",
            )

    axes[-1, 0].set_xlabel("Time (ns)", fontsize=10)
    fig.suptitle(
        f"{cfg['title']} by cluster (k={n_clusters_total})",
        fontsize=12,
        fontweight="bold",
        y=1.01,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return any_data


@tool
def plot_cluster_feature_trajectories(
    working_dir: str = "",
    assignments_file: str = "classification_cluster_assignments.csv",
    metric_groups: Optional[List[str]] = None,
    figsize_per_panel: Tuple[float, float] = (10.0, 3.0),
    dpi: int = 150,
) -> Dict[str, Any]:
    """
    Plot major classification feature trajectories with one subplot per cluster.

    After ``cluster_classification_features`` assigns simulations to k groups,
    this tool reads per-simulation time series (pocket SASA, COM distance,
    contacts, ligand residence) and writes one PNG per metric. Each PNG has
    k panels — one per cluster — with all proteins in that cluster overlaid.

    Per-residue metrics (pocket RMSF, ligand RMSF, FEL scalars) are skipped
    because they are not time series.

    Args:
        working_dir: Directory containing ``classification_cluster_assignments.csv``.
        assignments_file: Cluster assignment CSV from clustering step.
        metric_groups: Subset of ``com``, ``contacts``, ``pocket_sasa``,
            ``residence``. Defaults to all trajectory-capable groups.
        figsize_per_panel: Width and height (inches) for each cluster panel.
        dpi: Output image resolution.

    Returns:
        Dict with ``success``, ``plots`` (list of PNG paths), and ``metrics_plotted``.
    """
    try:
        assign_path = Path(assignments_file)
        if not assign_path.is_absolute():
            base = Path(working_dir) if working_dir else Path(".")
            assign_path = (base / assignments_file).resolve()
        if not assign_path.is_file():
            return {
                "success": False,
                "error": f"Assignments file not found: {assign_path}",
            }

        groups = tuple(
            g
            for g in (metric_groups or CLUSTER_TRAJECTORY_METRIC_GROUPS)
            if g in _CLUSTER_TRAJECTORY_CONFIG
        )
        if not groups:
            return {
                "success": False,
                "error": (
                    "No trajectory metric groups requested. "
                    f"Choose from: {', '.join(CLUSTER_TRAJECTORY_METRIC_GROUPS)}"
                ),
            }

        by_cluster, cluster_ids = _load_cluster_assignments(assign_path)
        if not cluster_ids:
            return {"success": False, "error": "No cluster assignments found"}

        out_dir = assign_path.parent
        plots: List[str] = []
        skipped: List[str] = []

        for metric_group in groups:
            cfg = _CLUSTER_TRAJECTORY_CONFIG[metric_group]
            output_path = out_dir / cfg["output_file"]
            ok = _plot_metric_by_cluster_panels(
                by_cluster,
                cluster_ids,
                metric_group,
                output_path,
                n_clusters_total=len(cluster_ids),
                figsize_per_panel=figsize_per_panel,
                dpi=dpi,
            )
            if ok:
                plots.append(str(output_path))
            else:
                skipped.append(metric_group)

        if not plots:
            return {
                "success": False,
                "error": "No trajectory plots generated (missing data or matplotlib)",
                "skipped_metrics": skipped,
            }

        return {
            "success": True,
            "message": (
                f"Cluster trajectory plots: {len(plots)} metric(s), "
                f"k={len(cluster_ids)} clusters"
            ),
            "plots": plots,
            "metrics_plotted": [
                g for g in groups if g not in skipped
            ],
            "skipped_metrics": skipped,
            "n_clusters": len(cluster_ids),
            "assignments_file": str(assign_path),
        }
    except Exception as exc:
        logger.exception("plot_cluster_feature_trajectories failed")
        return {"success": False, "error": str(exc)}


CLUSTER_RMSF_PROFILE_GROUPS: Tuple[str, ...] = (
    "pocket_rmsf",
    "ligand_rmsf",
)

_CLUSTER_RMSF_CONFIG: Dict[str, Dict[str, str]] = {
    "pocket_rmsf": {
        "file_pattern": "pocket_rmsf",
        "output_file": "pocket_rmsf_by_cluster.png",
        "title": "Pocket RMSF",
        "xlabel": "Pocket residue index",
        "ylabel": "RMSF (Å)",
    },
    "ligand_rmsf": {
        "file_pattern": "ligand_rmsf",
        "output_file": "ligand_rmsf_by_cluster.png",
        "title": "Ligand RMSF",
        "xlabel": "Ligand atom index",
        "ylabel": "RMSF (Å)",
    },
}


def _find_rmsf_profile_file(sim_directory: str, profile_type: str) -> Optional[str]:
    from src.analysis.combined_analysis import _find_binding_rmsf_file
    return _find_binding_rmsf_file(sim_directory, profile_type)


def _plot_rmsf_profiles_by_cluster_panels(
    by_cluster: Dict[int, List[Dict[str, str]]],
    cluster_ids: Sequence[int],
    profile_type: str,
    output_path: Path,
    n_clusters_total: int,
    figsize_per_panel: Tuple[float, float] = (10.0, 3.5),
    dpi: int = 150,
) -> bool:
    """One subplot per cluster with pocket/ligand RMSF profiles overlaid."""
    if not HAS_MPL:
        return False

    from src.analysis.data_plotter import _parse_rmsf_profile_dat

    cfg = _CLUSTER_RMSF_CONFIG[profile_type]
    n_panels = len(cluster_ids)
    fig, axes = plt.subplots(
        n_panels,
        1,
        figsize=(figsize_per_panel[0], figsize_per_panel[1] * n_panels),
        squeeze=False,
    )

    default_colors = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
        "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    ]
    any_data = False

    for idx, cid in enumerate(cluster_ids):
        ax = axes[idx, 0]
        members = by_cluster.get(cid, [])
        plotted = 0
        for mi, row in enumerate(members):
            sim_dir = row.get("sim_directory") or ""
            display_name = row.get("display_name") or row.get("label", "")
            if not sim_dir:
                continue
            fpath = _find_rmsf_profile_file(sim_dir, profile_type)
            if not fpath:
                continue
            profile = _parse_rmsf_profile_dat(fpath)
            if not profile:
                continue
            color = default_colors[mi % len(default_colors)]
            ax.plot(
                profile["x_positions"],
                profile["y_values"],
                label=display_name,
                color=color,
                linewidth=1.2,
                alpha=0.88,
            )
            plotted += 1
            any_data = True

        ax.set_ylabel(cfg["ylabel"], fontsize=9)
        ax.set_title(
            f"Cluster {cid} (n={len(members)}) — {cfg['title']}",
            fontsize=10,
            fontweight="bold",
        )
        ax.grid(True, alpha=0.3)
        if plotted:
            ax.legend(loc="best", fontsize=8, ncol=min(plotted, 3))
        else:
            ax.text(
                0.5, 0.5, "No RMSF data",
                transform=ax.transAxes, ha="center", va="center",
                fontsize=10, color="#666666",
            )

    axes[-1, 0].set_xlabel(cfg["xlabel"], fontsize=10)
    fig.suptitle(
        f"{cfg['title']} by cluster (k={n_clusters_total})",
        fontsize=12,
        fontweight="bold",
        y=1.01,
    )
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    return any_data


@tool
def plot_cluster_rmsf_profiles(
    working_dir: str = "",
    assignments_file: str = "classification_cluster_assignments.csv",
    profile_types: Optional[List[str]] = None,
    figsize_per_panel: Tuple[float, float] = (10.0, 3.5),
    dpi: int = 150,
) -> Dict[str, Any]:
    """
    Plot pocket and/or ligand RMSF profiles with one subplot per cluster.

    After clustering, overlays each protein's pocket/ligand RMSF curve within
    its assigned cluster panel (ordinal x-axis; legend uses display names).

    Args:
        working_dir: Directory with ``classification_cluster_assignments.csv``.
        assignments_file: Cluster assignment CSV.
        profile_types: ``pocket_rmsf``, ``ligand_rmsf``, or both (default).
        figsize_per_panel: Panel size in inches.
        dpi: Output resolution.

    Standard outputs: ``pocket_rmsf_by_cluster.png``, ``ligand_rmsf_by_cluster.png``.
    """
    try:
        assign_path = Path(assignments_file)
        if not assign_path.is_absolute():
            base = Path(working_dir) if working_dir else Path(".")
            assign_path = (base / assignments_file).resolve()
        if not assign_path.is_file():
            return {
                "success": False,
                "error": f"Assignments file not found: {assign_path}",
            }

        types = tuple(
            t for t in (profile_types or CLUSTER_RMSF_PROFILE_GROUPS)
            if t in _CLUSTER_RMSF_CONFIG
        )
        if not types:
            return {
                "success": False,
                "error": (
                    "No RMSF profile types requested. "
                    f"Choose from: {', '.join(CLUSTER_RMSF_PROFILE_GROUPS)}"
                ),
            }

        by_cluster, cluster_ids = _load_cluster_assignments(assign_path)
        if not cluster_ids:
            return {"success": False, "error": "No cluster assignments found"}

        out_dir = assign_path.parent
        plots: List[str] = []
        skipped: List[str] = []

        for profile_type in types:
            cfg = _CLUSTER_RMSF_CONFIG[profile_type]
            output_path = out_dir / cfg["output_file"]
            ok = _plot_rmsf_profiles_by_cluster_panels(
                by_cluster,
                cluster_ids,
                profile_type,
                output_path,
                n_clusters_total=len(cluster_ids),
                figsize_per_panel=figsize_per_panel,
                dpi=dpi,
            )
            if ok:
                plots.append(str(output_path))
            else:
                skipped.append(profile_type)

        if not plots:
            return {
                "success": False,
                "error": "No cluster RMSF plots generated",
                "skipped_profiles": skipped,
            }

        return {
            "success": True,
            "message": (
                f"Cluster RMSF plots: {len(plots)} profile(s), k={len(cluster_ids)} clusters"
            ),
            "plots": plots,
            "profiles_plotted": [t for t in types if t not in skipped],
            "skipped_profiles": skipped,
            "n_clusters": len(cluster_ids),
            "assignments_file": str(assign_path),
        }
    except Exception as exc:
        logger.exception("plot_cluster_rmsf_profiles failed")
        return {"success": False, "error": str(exc)}

