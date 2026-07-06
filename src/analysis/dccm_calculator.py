"""
DCCM Calculator - Dynamic Cross-Correlation Matrix analysis

Computes the normalised Dynamic Cross-Correlation Matrix (DCCM) of Cα
positional fluctuations over an MD trajectory using MDAnalysis.

The DCCM entry C_ij is defined as:

    C_ij = <Δr_i · Δr_j> / sqrt(<Δr_i²><Δr_j²>)

where Δr_i is the displacement vector of atom i from its time-averaged
position.  Values range from −1 (perfectly anti-correlated) to +1
(perfectly correlated).  Off-diagonal positive blocks indicate correlated
domains; negative blocks reveal breathing or hinge motions that are
particularly informative for pseudokinase comparisons.

Public @tool functions:
  1. calculate_dccm        — per-simulation DCCM + heatmap
  2. plot_dccm_comparison  — side-by-side heatmaps (+ optional Δ panel for 2 sims)
  3. plot_dccm_difference  — Δ DCCM heatmap (e.g. protein+ATP minus protein-only)
"""
import os
import csv
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from langchain.tools import tool
from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

# Fixed colour scales for combined DCCM figures (no per-matrix auto-normalisation).
DCCM_CORR_VMIN = -1.0
DCCM_CORR_VMAX = 1.0
DCCM_DIFF_VMIN = -1.0
DCCM_DIFF_VMAX = 1.0
DCCM_CMAP = "RdBu_r"
DCCM_DIFF_CMAP = "RdBu_r"

# ── Optional heavy dependencies ─────────────────────────────────────────────
try:
    import MDAnalysis as mda
    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    logger.warning("MDAnalysis not available — DCCM calculation will not work")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    logger.warning("matplotlib not available — DCCM plotting disabled")


# ── Internal helpers ─────────────────────────────────────────────────────────

def _compute_dccm_matrix(positions: "np.ndarray") -> "np.ndarray":
    """
    Compute the normalised DCCM from a (n_frames × n_atoms × 3) position array.

    Steps:
    1. Subtract per-atom mean position  → fluctuation vectors Δr (n×3)
    2. Compute covariance  <Δr_i · Δr_j>  (dot product means sum over x,y,z)
    3. Normalise by the geometric mean of the diagonal

    Returns a (n_atoms × n_atoms) array of float64.
    """
    n_frames, n_atoms, _ = positions.shape
    # Mean position for each atom
    mean_pos = positions.mean(axis=0)                        # (n_atoms, 3)
    delta = positions - mean_pos[np.newaxis, :, :]           # (n_frames, n_atoms, 3)

    # Covariance matrix: C[i,j] = sum_t (Δr_i(t) · Δr_j(t)) / n_frames
    # Reshape to (n_frames, n_atoms*3) and use matrix multiply
    flat = delta.reshape(n_frames, n_atoms * 3)              # (n_frames, n_atoms*3)
    # Group into blocks of 3
    # Equivalent: C[i,j] = (1/T) * sum_t ( Δr_i · Δr_j )
    # Using einsum for clarity and performance
    cov = np.einsum("tix,tjx->ij", delta, delta) / n_frames  # (n_atoms, n_atoms)

    # Normalise
    diag = np.diag(cov).copy()
    diag[diag <= 0] = 1e-12                                   # avoid division by zero
    norm = np.sqrt(np.outer(diag, diag))
    dccm = cov / norm

    # Clip to [-1, 1] to correct any floating-point overshoot
    np.clip(dccm, -1.0, 1.0, out=dccm)
    return dccm


def _plot_dccm_heatmap(
    matrix: "np.ndarray",
    residue_ids: List[int],
    output_path: str,
    title: str = "DCCM",
    vmin: float = -1.0,
    vmax: float = 1.0,
    figsize=(8, 7),
    dpi: int = 200,
    cmap: str = "RdBu_r",
) -> None:
    """Save a single DCCM heatmap as a PNG file."""
    fig, ax = plt.subplots(figsize=figsize)
    im = ax.imshow(
        matrix, cmap=cmap, vmin=vmin, vmax=vmax,
        aspect="auto", interpolation="nearest",
        origin="lower",
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.set_label("Correlation (C$_{ij}$)", fontsize=10)

    # X / Y ticks — show every Nth residue to keep labels readable
    n = len(residue_ids)
    step = max(1, n // 10)
    tick_pos = list(range(0, n, step))
    tick_labels = [str(residue_ids[i]) for i in tick_pos]
    ax.set_xticks(tick_pos)
    ax.set_xticklabels(tick_labels, fontsize=7, rotation=45, ha="right")
    ax.set_yticks(tick_pos)
    ax.set_yticklabels(tick_labels, fontsize=7)

    ax.set_xlabel("Residue index", fontsize=10)
    ax.set_ylabel("Residue index", fontsize=10)
    ax.set_title(title, fontsize=12, fontweight="bold")

    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _align_dccm_pair(
    matrix_a: "np.ndarray",
    residue_ids_a: List[int],
    matrix_b: "np.ndarray",
    residue_ids_b: List[int],
) -> Tuple["np.ndarray", "np.ndarray", List[int]]:
    """
    Reindex two DCCM matrices onto the intersection of residue IDs (sorted).

    Use this when comparing protein-only vs protein+ligand trajectories so
    axes match by residue number, not matrix truncation.
    """
    common = sorted(set(residue_ids_a) & set(residue_ids_b))
    if len(common) < 2:
        raise ValueError(
            f"Fewer than 2 common residues between DCCM matrices "
            f"({len(common)} shared IDs)"
        )
    idx_a = {r: i for i, r in enumerate(residue_ids_a)}
    idx_b = {r: i for i, r in enumerate(residue_ids_b)}
    n = len(common)
    aligned_a = np.zeros((n, n), dtype=np.float64)
    aligned_b = np.zeros((n, n), dtype=np.float64)
    for i, ri in enumerate(common):
        for j, rj in enumerate(common):
            aligned_a[i, j] = matrix_a[idx_a[ri], idx_a[rj]]
            aligned_b[i, j] = matrix_b[idx_b[ri], idx_b[rj]]
    return aligned_a, aligned_b, common


def _align_dccm_matrices(
    matrices: List["np.ndarray"],
    residue_sets: List[List[int]],
) -> Tuple[List["np.ndarray"], List[int]]:
    """Align multiple DCCM matrices to the intersection of all residue IDs."""
    if not matrices:
        raise ValueError("No DCCM matrices to align")
    common = sorted(set(residue_sets[0]))
    for res in residue_sets[1:]:
        common = sorted(set(common) & set(res))
    if len(common) < 2:
        raise ValueError(
            f"Fewer than 2 common residues across DCCM matrices ({len(common)} shared)"
        )
    aligned: List[np.ndarray] = []
    for mat, res_ids in zip(matrices, residue_sets):
        idx_map = {r: i for i, r in enumerate(res_ids)}
        n = len(common)
        out = np.zeros((n, n), dtype=np.float64)
        for i, ri in enumerate(common):
            for j, rj in enumerate(common):
                out[i, j] = mat[idx_map[ri], idx_map[rj]]
        aligned.append(out)
    return aligned, common


def _save_dccm_csv(
    matrix: "np.ndarray",
    residue_ids: List[int],
    output_path: str,
) -> None:
    """Save the full DCCM matrix to a CSV (residue_i, residue_j, correlation)."""
    n = len(residue_ids)
    with open(output_path, "w", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["residue_i", "residue_j", "correlation"])
        for i in range(n):
            for j in range(n):
                writer.writerow([residue_ids[i], residue_ids[j],
                                  round(float(matrix[i, j]), 4)])


# ── Public @tool functions ───────────────────────────────────────────────────

def compute_dccm_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    output_prefix: Optional[str] = None,
    frame_interval: int = 1,
    save_matrix_csv: bool = True,
    create_heatmap: bool = True,
    vmin: float = -1.0,
    vmax: float = 1.0,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute DCCM from a pre-loaded (typically aligned) Universe."""
    if not HAS_MDA or not HAS_NUMPY:
        return {"success": False, "error": "MDAnalysis and NumPy are required for DCCM"}

    prefix = output_prefix or "dccm"
    atoms = u.select_atoms(selection)
    if len(atoms) == 0:
        return {"success": False, "error": f"Selection '{selection}' matched 0 atoms"}

    n_total = len(u.trajectory)
    frame_indices = list(range(0, n_total, frame_interval))
    n_frames = len(frame_indices)
    n_atoms = len(atoms)
    positions = np.zeros((n_frames, n_atoms, 3), dtype=np.float64)

    for out_idx, ts_idx in enumerate(frame_indices):
        u.trajectory[ts_idx]
        positions[out_idx] = atoms.positions.copy()

    dccm = _compute_dccm_matrix(positions)
    residue_ids = [int(r.resid) for r in atoms.residues]

    strong_pairs = []
    for i in range(n_atoms):
        for j in range(i + 1, n_atoms):
            v = float(dccm[i, j])
            if abs(v) > 0.7:
                strong_pairs.append({
                    "residue_i": residue_ids[i],
                    "residue_j": residue_ids[j],
                    "correlation": round(v, 3),
                })
    strong_pairs.sort(key=lambda x: abs(x["correlation"]), reverse=True)
    strong_pairs = strong_pairs[:50]
    mean_abs_corr = float(np.abs(dccm[np.triu_indices(n_atoms, k=1)]).mean())

    output_files: Dict[str, str] = {}
    csv_path = None
    if save_matrix_csv:
        csv_name = f"{prefix}.csv"
        csv_path = str(Path(working_dir) / csv_name) if working_dir else csv_name
        _save_dccm_csv(dccm, residue_ids, csv_path)
        output_files["csv"] = csv_path

    heatmap_path = None
    if create_heatmap and HAS_MATPLOTLIB:
        heatmap_name = f"{prefix}_heatmap.png"
        heatmap_path = str(Path(working_dir) / heatmap_name) if working_dir else heatmap_name
        _plot_dccm_heatmap(
            dccm, residue_ids, heatmap_path,
            title=f"DCCM — {prefix}",
            vmin=vmin, vmax=vmax,
        )
        output_files["heatmap"] = heatmap_path

    if working_dir:
        append_analysis_summary(
            working_dir=working_dir,
            analysis_type="DCCM",
            statistics={
                "n_atoms": n_atoms,
                "n_residues": len(residue_ids),
                "n_frames_used": n_frames,
                "mean_abs_correlation": round(mean_abs_corr, 3),
                "n_strongly_correlated_pairs": len(strong_pairs),
            },
            files={
                "topology_file": topology_file,
                "trajectory_file": trajectory_file,
                "csv_file": csv_path or "not_saved",
                "heatmap_file": heatmap_path or "not_generated",
            },
            metadata={
                "selection": selection,
                "frame_interval": frame_interval,
                "top_correlated_pairs": strong_pairs[:5],
                "aligned_pass": True,
            },
        )

    return {
        "success": True,
        "n_atoms": n_atoms,
        "n_residues": len(residue_ids),
        "n_frames_used": n_frames,
        "residue_ids": residue_ids,
        "mean_abs_correlation": round(mean_abs_corr, 3),
        "strongly_correlated_pairs": strong_pairs,
        "output_files": output_files,
        "message": (
            f"DCCM computed for {n_atoms} Cα atoms over {n_frames} frames. "
            f"Mean |C_ij| = {mean_abs_corr:.3f}."
        ),
    }


@tool
def calculate_dccm(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    output_prefix: Optional[str] = None,
    frame_interval: int = 1,
    save_matrix_csv: bool = True,
    create_heatmap: bool = True,
    vmin: float = -1.0,
    vmax: float = 1.0,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Compute the Dynamic Cross-Correlation Matrix (DCCM) of Cα fluctuations.

    The DCCM quantifies how pairs of residues move together (correlated,
    C_ij → +1) or in opposite directions (anti-correlated, C_ij → −1)
    over the trajectory.  It is particularly informative for pseudokinase
    comparisons because it reveals differences in allosteric communication
    and activation-loop dynamics.

    Algorithm:
    1. Select Cα atoms (or user-defined selection) and trajectory-align
       them to the first frame to remove rigid-body motion.
    2. Collect per-frame Cα positions → (n_frames × n_atoms × 3) array.
    3. Compute normalised covariance matrix using displacement vectors.
    4. Write a CSV of the full matrix and a heatmap PNG.

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr) — full path.
        trajectory_file: Trajectory file (.xtc, .trr, .dcd) — full path.
        selection: MDAnalysis selection for DCCM atoms
            (default: ``"protein and name CA"`` — Cα for standard proteins).
        output_prefix: Filename prefix for output files (default: ``"dccm"``).
            Generates ``<prefix>.csv`` and ``<prefix>_heatmap.png``.
        frame_interval: Use every Nth frame (default: 1 = every frame).
            Set to 10 for a quick scan of long trajectories.
        save_matrix_csv: Write the full N×N matrix to CSV (default: True).
            May be large for proteins > 500 residues.
        create_heatmap: Generate a heatmap PNG (default: True).
        vmin: Colour scale minimum (default: −1.0).
        vmax: Colour scale maximum (default: +1.0).
        working_dir: Directory for output files.

    Returns:
        Dict with keys:
            success (bool), n_atoms (int), n_frames_used (int),
            n_residues (int), residue_ids (list[int]),
            mean_abs_correlation (float),
            strongly_correlated_pairs (list of {i, j, correlation} where |C|>0.7),
            output_files (dict with "csv" and/or "heatmap" paths),
            message (str).
    """
    if not HAS_MDA:
        return {"success": False, "error": "MDAnalysis not available"}
    if not HAS_NUMPY:
        return {"success": False, "error": "NumPy not available"}

    # ── Resolve paths ────────────────────────────────────────────────────────
    if working_dir:
        os.makedirs(working_dir, exist_ok=True)
        topology_file = _resolve_path(topology_file, working_dir)
        trajectory_file = _resolve_path(trajectory_file, working_dir)

    if not os.path.exists(topology_file):
        return {"success": False, "error": f"Topology not found: {topology_file}"}
    if not os.path.exists(trajectory_file):
        return {"success": False, "error": f"Trajectory not found: {trajectory_file}"}

    prefix = output_prefix or "dccm"

    try:
        u = mda.Universe(topology_file, trajectory_file)
        return compute_dccm_from_universe(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            selection=selection,
            output_prefix=prefix,
            frame_interval=frame_interval,
            save_matrix_csv=save_matrix_csv,
            create_heatmap=create_heatmap,
            vmin=vmin,
            vmax=vmax,
            working_dir=working_dir,
        )

    except Exception as e:
        import traceback
        logger.error(f"calculate_dccm failed: {e}\n{traceback.format_exc()}")
        return {"success": False, "error": str(e)}


@tool
def plot_dccm_comparison(
    dccm_files: List[str],
    labels: List[str],
    output_file: str,
    working_dir: str,
    vmin: float = DCCM_CORR_VMIN,
    vmax: float = DCCM_CORR_VMAX,
    diff_vmin: float = DCCM_DIFF_VMIN,
    diff_vmax: float = DCCM_DIFF_VMAX,
    figsize_per_panel: float = 5.0,
    dpi: int = 200,
    cmap: str = DCCM_CMAP,
    cmap_diff: str = DCCM_DIFF_CMAP,
) -> Dict[str, Any]:
    """
    Create a side-by-side comparison heatmap of DCCM matrices from multiple
    simulations for combined / multi-simulation reports.

    Reads the per-simulation DCCM CSV files produced by ``calculate_dccm``
    (columns: residue_i, residue_j, correlation) and renders them as a
    single multi-panel figure.  Residue axes are aligned across panels.

    A difference panel (last simulation minus first) is appended when exactly
    two simulations are compared **and** they share identical residue numbering
    (e.g. apo vs holo of the same protein). For cross-protein comparisons
    (JAK1 vs TYK2), each panel shows the full matrix and no Δ panel is drawn
    because residue indices are not structurally equivalent.

    Args:
        dccm_files: Ordered list of DCCM CSV file paths (one per simulation).
            Each file must have columns ``residue_i, residue_j, correlation``.
        labels: Human-readable labels (one per file, same order).
        output_file: Output image filename (e.g. ``"dccm_comparison.png"``).
            Saved inside *working_dir*.
        working_dir: Directory where the figure is written.
        vmin: Common colour scale minimum (default: −1.0).
        vmax: Common colour scale maximum (default: +1.0).
        figsize_per_panel: Width (and height) in inches for each panel
            (default: 5.0).
        dpi: Image resolution (default: 200).
        cmap: Matplotlib diverging colormap (default: ``"RdBu_r"``).

    Returns:
        Dict with ``success``, ``output_path``, ``n_panels``, ``message``.
    """
    if not HAS_NUMPY:
        return {"success": False, "error": "NumPy not available"}
    if not HAS_MATPLOTLIB:
        return {"success": False, "error": "matplotlib not available"}
    if len(dccm_files) != len(labels):
        return {"success": False,
                "error": "dccm_files and labels must have the same length"}

    Path(working_dir).mkdir(parents=True, exist_ok=True)
    output_path = str(Path(working_dir) / output_file)

    # ── Load matrices ────────────────────────────────────────────────────────
    matrices: List[np.ndarray] = []
    residue_sets: List[List[int]] = []

    for fpath in dccm_files:
        if not os.path.exists(fpath):
            return {"success": False,
                    "error": f"DCCM CSV not found: {fpath}"}
        try:
            mat, res_ids = _load_dccm_csv(fpath)
            matrices.append(mat)
            residue_sets.append(res_ids)
        except Exception as e:
            return {"success": False,
                    "error": f"Failed to read {fpath}: {e}"}

    # Same-protein runs (apo/holo, replicates) share residue IDs → align + optional Δ.
    # Cross-protein comparisons keep each full matrix; no Δ panel.
    same_numbering = (
        len(residue_sets) >= 2
        and all(set(residue_sets[0]) == set(rs) for rs in residue_sets[1:])
    )
    if same_numbering:
        try:
            matrices, residue_ids = _align_dccm_matrices(matrices, residue_sets)
        except ValueError as e:
            return {"success": False, "error": str(e)}
        panel_residue_sets: List[List[int]] = [residue_ids] * len(matrices)
        add_diff = len(matrices) == 2
        n_residues = len(residue_ids)
    else:
        panel_residue_sets = residue_sets
        add_diff = False
        n_residues = max(len(rs) for rs in residue_sets)

    n_panels = len(matrices) + (1 if add_diff else 0)

    fig, axes = plt.subplots(
        1, n_panels,
        figsize=(figsize_per_panel * n_panels + 1, figsize_per_panel + 1),
    )
    if n_panels == 1:
        axes = [axes]

    for ax, mat, label, res_ids in zip(
        axes[: len(matrices)], matrices, labels, panel_residue_sets
    ):
        n = len(res_ids)
        step = max(1, n // 8)
        tick_pos = list(range(0, n, step))
        tick_labels = [str(res_ids[i]) for i in tick_pos]
        im = ax.imshow(
            mat, cmap=cmap, vmin=vmin, vmax=vmax,
            aspect="auto", interpolation="nearest", origin="lower",
        )
        ax.set_title(label, fontsize=10, fontweight="bold")
        ax.set_xticks(tick_pos)
        ax.set_xticklabels(tick_labels, fontsize=6, rotation=45, ha="right")
        ax.set_yticks(tick_pos)
        ax.set_yticklabels(tick_labels, fontsize=6)
        ax.set_xlabel("Residue", fontsize=8)
        ax.set_ylabel("Residue", fontsize=8)

    # ── Shared colorbar on the last matrix panel ─────────────────────────────
    cbar_ax = axes[len(matrices) - 1]
    sm = plt.cm.ScalarMappable(cmap=cmap, norm=mcolors.Normalize(vmin=vmin, vmax=vmax))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=cbar_ax, fraction=0.046, pad=0.04)
    cbar.set_label("C$_{ij}$", fontsize=9)

    # ── Optional difference panel (same protein / identical numbering only) ─
    if add_diff:
        diff = matrices[1] - matrices[0]
        ax_diff = axes[-1]
        step = max(1, n_residues // 8)
        tick_pos = list(range(0, n_residues, step))
        tick_labels = [str(panel_residue_sets[0][i]) for i in tick_pos]
        im_diff = ax_diff.imshow(
            diff, cmap=cmap_diff, vmin=diff_vmin, vmax=diff_vmax,
            aspect="auto", interpolation="nearest", origin="lower",
        )
        ax_diff.set_title(f"Δ ({labels[1]} − {labels[0]})", fontsize=10)
        ax_diff.set_xticks(tick_pos)
        ax_diff.set_xticklabels(tick_labels, fontsize=6, rotation=45, ha="right")
        ax_diff.set_yticks(tick_pos)
        ax_diff.set_yticklabels(tick_labels, fontsize=6)
        ax_diff.set_xlabel("Residue", fontsize=8)
        cbar_diff = fig.colorbar(im_diff, ax=ax_diff, fraction=0.046, pad=0.04)
        cbar_diff.set_label("ΔC$_{ij}$", fontsize=9)

    title = "Dynamic Cross-Correlation Matrix Comparison"
    if len(matrices) == 2 and not add_diff:
        title += " (cross-protein: no Δ panel — residue numbers are not equivalent)"
    fig.suptitle(title, fontsize=13, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(output_path, dpi=dpi, bbox_inches="tight")
    plt.close(fig)

    return {
        "success": True,
        "output_path": output_path,
        "n_panels": n_panels,
        "n_residues_aligned": n_residues,
        "difference_panel": add_diff,
        "same_residue_numbering": same_numbering,
        "message": (
            f"DCCM comparison figure ({n_panels} panels, "
            f"{'aligned ' if same_numbering else ''}{n_residues} residues) "
            f"saved to {output_path}"
        ),
    }


@tool
def plot_dccm_difference(
    reference_dccm_file: str,
    compare_dccm_file: str,
    reference_label: str = "Reference",
    compare_label: str = "Compare",
    output_prefix: str = "dccm_difference",
    working_dir: Optional[str] = None,
    plot_mode: str = "difference_only",
    diff_threshold: float = 0.3,
    max_top_pairs: int = 50,
    dpi: int = 200,
    vmin_corr: float = DCCM_CORR_VMIN,
    vmax_corr: float = DCCM_CORR_VMAX,
    diff_vmin: float = DCCM_DIFF_VMIN,
    diff_vmax: float = DCCM_DIFF_VMAX,
    cmap_corr: str = DCCM_CMAP,
    cmap_diff: str = DCCM_DIFF_CMAP,
) -> Dict[str, Any]:
    """
    Compute and plot the difference between two DCCM matrices (ΔC = compare − reference).

    Typical use: quantify how ATP (or another ligand) changes protein correlated
    motions by comparing DCCM from ``protein only`` vs ``protein + ATP`` simulations.
    Run ``calculate_dccm`` on each trajectory first (same ``selection``, e.g.
    ``"protein and name CA"``), then pass the two CSV files here.

    Residue axes are aligned on the **intersection** of residue IDs in both CSVs,
    so protein-only and protein+ligand systems match by residue number.

    Args:
        reference_dccm_file: Baseline DCCM CSV (e.g. protein-only ``dccm.csv``).
        compare_dccm_file: Perturbed DCCM CSV (e.g. protein+ATP ``dccm.csv``).
        reference_label: Label for baseline (plots / legend).
        compare_label: Label for perturbed system.
        output_prefix: Prefix for outputs: ``<prefix>.csv``, ``<prefix>_heatmap.png``,
            and (if ``plot_mode="with_matrices"``) ``<prefix>_panels.png``.
        working_dir: Directory for output files.
        plot_mode: ``"difference_only"`` (default) — single Δ heatmap;
            ``"with_matrices"`` — reference, compare, and Δ in one figure.
        diff_threshold: Report residue pairs with |ΔC| above this (default: 0.3).
        max_top_pairs: Cap on reported pairs (default: 50).
        dpi: PNG resolution.

    Returns:
        Dict with ``success``, ``delta_matrix_stats``, ``top_changed_pairs``,
        ``output_files``, ``n_residues_aligned``, ``message``.
    """
    if not HAS_NUMPY:
        return {"success": False, "error": "NumPy not available"}
    if not HAS_MATPLOTLIB:
        return {"success": False, "error": "matplotlib not available"}

    if plot_mode not in ("difference_only", "with_matrices"):
        return {
            "success": False,
            "error": "plot_mode must be 'difference_only' or 'with_matrices'",
        }

    if working_dir:
        Path(working_dir).mkdir(parents=True, exist_ok=True)
        reference_dccm_file = _resolve_path(reference_dccm_file, working_dir)
        compare_dccm_file = _resolve_path(compare_dccm_file, working_dir)

    for fpath, name in [
        (reference_dccm_file, "reference_dccm_file"),
        (compare_dccm_file, "compare_dccm_file"),
    ]:
        if not os.path.exists(fpath):
            return {"success": False, "error": f"{name} not found: {fpath}"}

    try:
        mat_ref, res_ref = _load_dccm_csv(reference_dccm_file)
        mat_cmp, res_cmp = _load_dccm_csv(compare_dccm_file)
        mat_ref, mat_cmp, residue_ids = _align_dccm_pair(
            mat_ref, res_ref, mat_cmp, res_cmp
        )
        diff = mat_cmp - mat_ref
    except Exception as e:
        return {"success": False, "error": str(e)}

    n_residues = len(residue_ids)
    off_diag = diff[np.triu_indices(n_residues, k=1)]
    delta_stats = {
        "mean_abs_delta": round(float(np.abs(off_diag).mean()), 4),
        "max_delta": round(float(off_diag.max()), 4),
        "min_delta": round(float(off_diag.min()), 4),
    }

    top_pairs: List[Dict[str, Any]] = []
    for i in range(n_residues):
        for j in range(i + 1, n_residues):
            v = float(diff[i, j])
            if abs(v) >= diff_threshold:
                top_pairs.append({
                    "residue_i": residue_ids[i],
                    "residue_j": residue_ids[j],
                    "delta_correlation": round(v, 4),
                })
    top_pairs.sort(key=lambda x: abs(x["delta_correlation"]), reverse=True)
    top_pairs = top_pairs[:max_top_pairs]

    prefix = output_prefix or "dccm_difference"
    output_files: Dict[str, str] = {}

    if working_dir:
        csv_path = str(Path(working_dir) / f"{prefix}.csv")
        heatmap_path = str(Path(working_dir) / f"{prefix}_heatmap.png")
    else:
        csv_path = f"{prefix}.csv"
        heatmap_path = f"{prefix}_heatmap.png"

    _save_dccm_csv(diff, residue_ids, csv_path)
    output_files["delta_csv"] = csv_path

    diff_title = f"Δ DCCM ({compare_label} − {reference_label})"

    if plot_mode == "with_matrices":
        panels_path = (
            str(Path(working_dir) / f"{prefix}_panels.png")
            if working_dir
            else f"{prefix}_panels.png"
        )
        fig, axes = plt.subplots(
            1, 3, figsize=(16, 5.5),
        )
        n = n_residues
        step = max(1, n // 8)
        tick_pos = list(range(0, n, step))
        tick_labels = [str(residue_ids[i]) for i in tick_pos]

        for ax, mat, title in zip(
            axes[:2],
            [mat_ref, mat_cmp],
            [reference_label, compare_label],
        ):
            ax.imshow(
                mat, cmap=cmap_corr, vmin=vmin_corr, vmax=vmax_corr,
                aspect="auto", interpolation="nearest", origin="lower",
            )
            ax.set_title(title, fontsize=10, fontweight="bold")
            ax.set_xticks(tick_pos)
            ax.set_xticklabels(tick_labels, fontsize=6, rotation=45, ha="right")
            ax.set_yticks(tick_pos)
            ax.set_yticklabels(tick_labels, fontsize=6)
            ax.set_xlabel("Residue", fontsize=8)
            ax.set_ylabel("Residue", fontsize=8)

        ax_diff = axes[2]
        im_diff = ax_diff.imshow(
            diff, cmap=cmap_diff, vmin=diff_vmin, vmax=diff_vmax,
            aspect="auto", interpolation="nearest", origin="lower",
        )
        ax_diff.set_title(diff_title, fontsize=10, fontweight="bold")
        ax_diff.set_xticks(tick_pos)
        ax_diff.set_xticklabels(tick_labels, fontsize=6, rotation=45, ha="right")
        ax_diff.set_yticks(tick_pos)
        ax_diff.set_yticklabels(tick_labels, fontsize=6)
        ax_diff.set_xlabel("Residue", fontsize=8)
        fig.colorbar(im_diff, ax=ax_diff, fraction=0.046, pad=0.04).set_label(
            "ΔC$_{ij}$", fontsize=9
        )
        fig.suptitle(
            "DCCM difference — ligand / condition effect on dynamics",
            fontsize=12, fontweight="bold", y=1.02,
        )
        plt.tight_layout()
        plt.savefig(panels_path, dpi=dpi, bbox_inches="tight")
        plt.close(fig)
        output_files["panels"] = panels_path

    _plot_dccm_heatmap(
        diff, residue_ids, heatmap_path,
        title=diff_title,
        vmin=diff_vmin, vmax=diff_vmax,
        cmap=cmap_diff,
        figsize=(8, 7),
        dpi=dpi,
    )
    output_files["heatmap"] = heatmap_path

    if working_dir:
        append_analysis_summary(
            working_dir=working_dir,
            analysis_type="DCCM_Difference",
            statistics={
                "n_residues_aligned": n_residues,
                **delta_stats,
                "n_pairs_above_threshold": len(top_pairs),
            },
            files={
                "reference_dccm_csv": reference_dccm_file,
                "compare_dccm_csv": compare_dccm_file,
                "delta_csv": csv_path,
                "heatmap_file": heatmap_path,
            },
            metadata={
                "reference_label": reference_label,
                "compare_label": compare_label,
                "diff_threshold": diff_threshold,
                "top_changed_pairs": top_pairs[:10],
            },
        )

    return {
        "success": True,
        "n_residues_aligned": n_residues,
        "residue_id_range": [residue_ids[0], residue_ids[-1]] if residue_ids else [],
        "delta_matrix_stats": delta_stats,
        "top_changed_pairs": top_pairs,
        "output_files": output_files,
        "message": (
            f"DCCM difference ({compare_label} − {reference_label}) for "
            f"{n_residues} aligned residues. "
            f"Mean |ΔC| = {delta_stats['mean_abs_delta']:.3f}. "
            f"{len(top_pairs)} pairs with |ΔC| ≥ {diff_threshold}."
        ),
    }


# ── Private loading helper ───────────────────────────────────────────────────

def _load_dccm_csv(fpath: str):
    """
    Read a DCCM CSV file (columns: residue_i, residue_j, correlation)
    and return (matrix_2d, residue_ids_list).
    """
    import csv as _csv

    data: Dict[tuple, float] = {}
    res_set = set()

    with open(fpath, newline="", encoding="utf-8") as fh:
        reader = _csv.DictReader(fh)
        for row in reader:
            ri = int(row["residue_i"])
            rj = int(row["residue_j"])
            c = float(row["correlation"])
            data[(ri, rj)] = c
            res_set.add(ri)
            res_set.add(rj)

    residue_ids = sorted(res_set)
    n = len(residue_ids)
    idx_map = {r: i for i, r in enumerate(residue_ids)}

    matrix = np.zeros((n, n), dtype=np.float64)
    for (ri, rj), c in data.items():
        i, j = idx_map[ri], idx_map[rj]
        matrix[i, j] = c
        matrix[j, i] = c  # symmetrise

    return matrix, residue_ids


# ── Path resolution helper (shared pattern) ──────────────────────────────────

def _resolve_path(filename: str, working_dir: str) -> str:
    """
    If *filename* is already an absolute / relative path that exists, return
    it unchanged.  Otherwise search in *working_dir* and its subdirectories.
    """
    if os.path.isabs(filename) and os.path.exists(filename):
        return filename
    if os.path.exists(filename):
        return os.path.abspath(filename)
    # Search in working_dir
    for candidate in Path(working_dir).rglob(Path(filename).name):
        return str(candidate)
    # Last resort: prepend working_dir
    return str(Path(working_dir) / filename)
