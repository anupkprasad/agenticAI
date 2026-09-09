"""
PCA and free-energy landscape (FEL) analysis for MD trajectories.

Workflow:
  1. ``calculate_trajectory_pca`` — align, PCA on Cα (or custom) coordinates, save projections
  2. ``plot_pca_projection`` — PC1 vs PC2 scatter (coloured by time)
  3. ``calculate_free_energy_landscape`` — 2D histogram in PC1/PC2 → F = −kT ln P

Uses MDAnalysis ``analysis.pca.PCA`` when available (recommended).
"""
from __future__ import annotations

import csv
import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis.pca import PCA as MDAPCA

    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    logger.warning("MDAnalysis not available — PCA analysis disabled")

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    LinearSegmentedColormap = None  # type: ignore[misc, assignment]
    logger.warning("matplotlib not available — PCA/FEL plotting disabled")

# Boltzmann constant in kJ/(mol·K) for ΔG = kT ln P landscapes
_KB_KJ_MOL_K = 0.00831446261815324

# Canonical PCA/FEL defaults — enforced across all simulations unless the user goal
# explicitly requests different values (see resolve_pca_overrides_from_goal).
PCA_TOOL_DEFAULTS: Dict[str, Dict[str, Any]] = {
    "calculate_trajectory_pca": {
        "selection": "protein and name CA",
        "n_components": 10,
        "reference_frame": 0,
        "frame_interval": 1,
        "projections_file": "pca_projections.dat",
        "variance_file": "pca_variance.dat",
    },
    "plot_pca_projection": {
        "pc_x": 1,
        "pc_y": 2,
        "output_file": "pca_pc1_pc2.png",
    },
    "calculate_free_energy_landscape": {
        "pc_x": 1,
        "pc_y": 2,
        "bins": 50,
        "temperature_k": 310.0,
        "output_plot": "fel_pc1_pc2.png",
        "output_grid": "fel_pc1_pc2_grid.csv",
    },
    "analyze_fel_landscape_features": {
        "pc_x": 1,
        "pc_y": 2,
        "bins": 50,
        "temperature_k": 310.0,
        "smooth_sigma": 2.0,
        "min_basin_population": 0.05,
        "min_prominence_kj_mol": 1.5,
        "fel_grid_file": "fel_pc1_pc2_grid.csv",
        "output_json": "fel_features.json",
        "output_csv": "fel_features.csv",
        "output_basins_csv": "fel_basins.csv",
    },
}


def resolve_pca_overrides_from_goal(user_goal: str) -> Dict[str, Any]:
    """Return PCA/FEL parameter overrides only when the user goal explicitly asks."""
    import re

    if not user_goal:
        return {}

    goal = user_goal.lower()
    overrides: Dict[str, Any] = {}

    m = re.search(r"n[_\s-]?components?\s*[=:]\s*(\d+)", goal)
    if not m:
        m = re.search(r"\b(\d+)\s*(?:principal\s+)?components?\b", goal)
    if m:
        overrides["n_components"] = int(m.group(1))

    m = re.search(r"frame[_\s-]?interval\s*[=:]\s*(\d+)", goal)
    if not m:
        m = re.search(r"every\s+(\d+)(?:st|nd|rd|th)?\s+frame", goal)
    if m:
        overrides["frame_interval"] = int(m.group(1))

    m = re.search(r"(?:temperature|temp\.?|fel|free[\s-]?energy)\s*(?:at|@|=|:)?\s*(\d+(?:\.\d+)?)\s*k\b", goal)
    if not m:
        m = re.search(r"\b(\d+(?:\.\d+)?)\s*k\b", goal)
    if m and any(kw in goal for kw in ("fel", "free energy", "free-energy", "landscape", "310")):
        overrides["temperature_k"] = float(m.group(1))

    m = re.search(r"\b(\d+)\s*bins?\b", goal)
    if m and "bin" in goal:
        overrides["bins"] = int(m.group(1))

    return overrides


def apply_pca_tool_defaults(
    tool_name: str, kwargs: Dict[str, Any], user_goal: str = ""
) -> Dict[str, Any]:
    """
    Merge canonical PCA/FEL defaults; user-goal overrides beat LLM plan params.

    Args:
        tool_name: Name of the PCA/FEL tool to normalize.
        kwargs: Tool kwargs proposed by planner/LLM.
        user_goal: Original user goal text used for explicit override extraction.

    Returns:
        Dict of normalized kwargs for the requested tool.
    """
    defaults = PCA_TOOL_DEFAULTS.get(tool_name)
    if not defaults:
        return kwargs
    merged = dict(kwargs)
    merged.update(defaults)
    overrides = resolve_pca_overrides_from_goal(user_goal)
    # Goal overrides (e.g. temperature_k from "310 K") apply only to keys this tool uses.
    merged.update({k: v for k, v in overrides.items() if k in defaults})
    return merged


def _chdir_working(working_dir: Optional[str]):
    if working_dir:
        os.makedirs(working_dir, exist_ok=True)
        original = os.getcwd()
        os.chdir(working_dir)
        return original
    return None


def _restore_cwd(original_dir: Optional[str]) -> None:
    if original_dir:
        os.chdir(original_dir)


def _run_trajectory_pca(
    topology_file: str,
    trajectory_file: str,
    *,
    selection: str = "protein and name CA",
    n_components: int = 10,
    reference_frame: int = 0,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    """Core PCA: returns projections (n_frames, n_pc), variance, times_ps."""
    if not HAS_MDA:
        return {"success": False, "error": "MDAnalysis is required for trajectory PCA"}

    u = mda.Universe(topology_file, trajectory_file)
    n_frames_total = len(u.trajectory)
    if n_frames_total < 2:
        return {
            "success": False,
            "error": f"Trajectory has only {n_frames_total} frame(s); need ≥ 2 for PCA",
        }

    ref_idx = max(0, min(int(reference_frame), n_frames_total - 1))
    if ref_idx != 0:
        from MDAnalysis.analysis import align

        ref = mda.Universe(topology_file, trajectory_file)
        ref.trajectory[ref_idx]
        align.AlignTraj(u, ref, select=selection, in_memory=True).run()

    n_components = min(int(n_components), max(1, n_frames_total - 1))
    step = max(1, int(frame_interval))

    pca = MDAPCA(
        u,
        select=selection,
        align=(ref_idx == 0),
        n_components=n_components,
    )
    pca.run(start=0, stop=None, step=step)

    atomgroup = u.select_atoms(selection)
    if hasattr(pca.results, "pca"):
        # MDAnalysis < 2.0 legacy
        projections = np.asarray(pca.results.pca, dtype=float)
    else:
        projections = np.asarray(
            pca.transform(
                atomgroup,
                n_components=n_components,
                start=0,
                stop=None,
                step=step,
                verbose=False,
            ),
            dtype=float,
        )

    variance = np.asarray(pca.results.variance, dtype=float)
    if hasattr(pca.results, "cumulated_variance"):
        cumvar = np.asarray(pca.results.cumulated_variance, dtype=float)
    else:
        cumvar = np.cumsum(variance) / max(np.sum(variance), 1e-12)

    # Times for sampled frames
    times_ps: List[float] = []
    for i, ts in enumerate(u.trajectory[::step]):
        if i >= projections.shape[0]:
            break
        times_ps.append(float(ts.time))

    if len(times_ps) < projections.shape[0]:
        # Pad if trajectory iterator shorter than PCA rows
        dt = (times_ps[-1] - times_ps[0]) / max(1, len(times_ps) - 1) if len(times_ps) > 1 else 0.0
        while len(times_ps) < projections.shape[0]:
            times_ps.append(times_ps[-1] + dt if times_ps else 0.0)

    return {
        "success": True,
        "projections": projections,
        "variance": variance,
        "cumulative_variance": cumvar,
        "times_ps": np.asarray(times_ps[: projections.shape[0]]),
        "n_components": projections.shape[1] if projections.ndim > 1 else 1,
        "n_frames": projections.shape[0],
        "selection": selection,
    }


def _write_pca_tables(
    projections: np.ndarray,
    variance: np.ndarray,
    cumulative: np.ndarray,
    times_ps: np.ndarray,
    *,
    projections_file: str = "pca_projections.dat",
    variance_file: str = "pca_variance.dat",
) -> Tuple[str, str]:
    n_pc = projections.shape[1]
    header = "\t".join(["frame", "time_ns"] + [f"PC{i + 1}" for i in range(n_pc)])

    with open(projections_file, "w", encoding="utf-8") as fh:
        fh.write(f"# {header}\n")
        for i in range(projections.shape[0]):
            t_ns = times_ps[i] / 1000.0
            pcs = "\t".join(f"{projections[i, j]:.6f}" for j in range(n_pc))
            fh.write(f"{i}\t{t_ns:.6f}\t{pcs}\n")

    with open(variance_file, "w", encoding="utf-8") as fh:
        fh.write("# PC\tvariance_A2\tcumulative_fraction\n")
        for i in range(len(variance)):
            fh.write(f"{i + 1}\t{variance[i]:.6f}\t{cumulative[i]:.6f}\n")

    return projections_file, variance_file


def load_pca_projections(path: str) -> Dict[str, Any]:
    """Load ``pca_projections.dat`` written by ``calculate_trajectory_pca``."""
    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"PCA projections file not found: {path}"}

    times_ns: List[float] = []
    frame_indices: List[int] = []
    rows: List[List[float]] = []
    pc_labels: List[str] = []

    with open(p, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                if line.startswith("#") and "PC1" in line:
                    parts = line.lstrip("#").strip().split("\t")
                    pc_labels = [c for c in parts if c.startswith("PC")]
                continue
            cols = line.split("\t")
            if len(cols) < 3:
                continue
            frame_indices.append(int(float(cols[0])))
            times_ns.append(float(cols[1]))
            rows.append([float(x) for x in cols[2:]])

    if not rows:
        return {"success": False, "error": f"No data rows in {path}"}

    projections = np.asarray(rows, dtype=float)
    if not pc_labels:
        pc_labels = [f"PC{i + 1}" for i in range(projections.shape[1])]

    return {
        "success": True,
        "projections": projections,
        "times_ns": np.asarray(times_ns),
        "frame_indices": np.asarray(frame_indices, dtype=int),
        "pc_labels": pc_labels,
        "path": str(p.resolve()),
    }


def _compute_free_energy_grid(
    pc_x: np.ndarray,
    pc_y: np.ndarray,
    *,
    bins: int = 50,
    temperature_k: float = 310.0,
) -> Dict[str, Any]:
    """2D histogram → probability → free energy F = −kT ln(P + ε)."""
    H, xedges, yedges = np.histogram2d(pc_x, pc_y, bins=bins)
    total = H.sum()
    if total <= 0:
        return {"success": False, "error": "Empty PC histogram — cannot build FEL"}

    P = H / total
    kT = _KB_KJ_MOL_K * float(temperature_k)
    eps = 1e-12
    F = -kT * np.log(P + eps)
    # Shift so minimum free energy is zero (common visualization convention)
    F = F - np.nanmin(F)

    xc = 0.5 * (xedges[:-1] + xedges[1:])
    yc = 0.5 * (yedges[:-1] + yedges[1:])

    return {
        "success": True,
        "free_energy": F,
        "probability": P,
        "x_centers": xc,
        "y_centers": yc,
        "xedges": xedges,
        "yedges": yedges,
        "temperature_k": temperature_k,
        "kT_kJ_mol": kT,
    }


@tool
def calculate_trajectory_pca(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    n_components: int = 10,
    reference_frame: int = 0,
    frame_interval: int = 1,
    projections_file: Optional[str] = None,
    variance_file: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Perform principal component analysis (PCA) on an aligned MD trajectory.

    Aligns structures to the reference frame, builds a covariance matrix of
    atomic positional fluctuations, and projects each frame onto the top
    principal components. Use the output with ``plot_pca_projection`` and
    ``calculate_free_energy_landscape``.

    **Typical workflow:** PCA → PC1/PC2 scatter → free-energy landscape (FEL).

    Args:
        topology_file: Topology (.gro, .pdb, .tpr) — full path.
        trajectory_file: Trajectory (.xtc, .trr) — full path.
        selection: Atoms for PCA (default: Cα protein).
        n_components: Number of PCs to keep (default 10).
        reference_frame: Alignment reference frame index (default 0).
        frame_interval: Use every Nth frame (default 1).
        projections_file: Output table (default ``pca_projections.dat``).
        variance_file: PC variance table (default ``pca_variance.dat``).
        working_dir: Output directory.

    Returns:
        Dict with variance explained, output paths, and PC1/PC2 ranges.

    Standard outputs: ``pca_projections.dat``, ``pca_variance.dat``.
    """
    original_dir = None
    try:
        original_dir = _chdir_working(working_dir)

        if not os.path.exists(topology_file):
            return {"success": False, "error": f"Topology file not found: {topology_file}"}
        if not os.path.exists(trajectory_file):
            return {"success": False, "error": f"Trajectory file not found: {trajectory_file}"}

        result = _run_trajectory_pca(
            topology_file,
            trajectory_file,
            selection=selection,
            n_components=n_components,
            reference_frame=reference_frame,
            frame_interval=frame_interval,
        )
        if not result.get("success"):
            return result

        proj_out = projections_file or "pca_projections.dat"
        var_out = variance_file or "pca_variance.dat"
        _write_pca_tables(
            result["projections"],
            result["variance"],
            result["cumulative_variance"],
            result["times_ps"],
            projections_file=proj_out,
            variance_file=var_out,
        )

        var = result["variance"]
        cum = result["cumulative_variance"]
        pc1_frac = float(cum[0]) if len(cum) else 0.0
        pc12_frac = float(cum[1]) if len(cum) > 1 else pc1_frac

        if working_dir:
            try:
                append_analysis_summary(
                    working_dir=working_dir,
                    analysis_type="PCA",
                    statistics={
                        "n_frames": result["n_frames"],
                        "n_components": result["n_components"],
                        "PC1_variance_A2": float(var[0]) if len(var) else None,
                        "PC1_cumulative_fraction": pc1_frac,
                        "PC1_PC2_cumulative_fraction": pc12_frac,
                    },
                    files={
                        "topology": topology_file,
                        "trajectory": trajectory_file,
                        "projections": proj_out,
                        "variance": var_out,
                    },
                    metadata={
                        "selection": selection,
                        "reference_frame": reference_frame,
                        "frame_interval": frame_interval,
                    },
                )
            except Exception as exc:
                logger.warning("Failed to write PCA summary: %s", exc)

        msg = (
            f"PCA complete: {result['n_frames']} frames, {result['n_components']} components; "
            f"PC1 explains {pc1_frac * 100:.1f}% cumulative variance"
        )
        if result["n_frames"] < 20:
            msg += " (warning: few frames — FEL may be noisy; prefer ≥ 50 frames)"

        return {
            "success": True,
            "message": msg,
            "n_frames": result["n_frames"],
            "n_components": result["n_components"],
            "PC1_variance_fraction": pc1_frac,
            "PC1_PC2_variance_fraction": pc12_frac,
            "projections_file": proj_out,
            "variance_file": var_out,
            "selection": selection,
        }
    except Exception as exc:
        logger.exception("PCA calculation failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original_dir)


@tool
def plot_pca_projection(
    pca_projections_file: str,
    pc_x: int = 1,
    pc_y: int = 2,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    color_by_time: bool = True,
) -> Dict[str, Any]:
    """
    Plot a 2D PCA projection (PCx vs PCy) from ``pca_projections.dat``.

    Points are coloured by simulation time when ``color_by_time=True`` (default),
    which helps visualise the temporal path through conformational space.

    Args:
        pca_projections_file: Path to projections table from ``calculate_trajectory_pca``.
        pc_x: First PC index (1-based, default 1).
        pc_y: Second PC index (1-based, default 2).
        output_file: PNG path (default ``pca_pc{pc_x}_pc{pc_y}.png``).
        working_dir: Directory for relative paths.
        color_by_time: Colour scatter by time (default True).

    Standard output: ``pca_pc1_pc2.png`` when pc_x=1, pc_y=2.
    """
    if not HAS_MATPLOTLIB:
        return {"success": False, "error": "matplotlib is required for PCA plots"}

    original_dir = None
    try:
        original_dir = _chdir_working(working_dir)

        loaded = load_pca_projections(pca_projections_file)
        if not loaded.get("success"):
            return loaded

        projections = loaded["projections"]
        times_ns = loaded["times_ns"]
        ix, iy = int(pc_x) - 1, int(pc_y) - 1
        if ix < 0 or iy < 0 or ix >= projections.shape[1] or iy >= projections.shape[1]:
            return {
                "success": False,
                "error": f"PC indices {pc_x}/{pc_y} out of range (have {projections.shape[1]} components)",
            }

        x = projections[:, ix]
        y = projections[:, iy]
        out = output_file or f"pca_pc{pc_x}_pc{pc_y}.png"

        fig, ax = plt.subplots(figsize=(7, 6))
        if color_by_time and len(times_ns) == len(x):
            sc = ax.scatter(x, y, c=times_ns, cmap="viridis", s=18, alpha=0.85, edgecolors="none")
            cbar = fig.colorbar(sc, ax=ax)
            cbar.set_label("Time (ns)")
        else:
            ax.scatter(x, y, s=18, alpha=0.85, c="#2563eb", edgecolors="none")
            for i in range(len(x)):
                ax.plot(x[i], y[i], "k.", markersize=2, alpha=0.3)

        ax.set_xlabel(f"PC{pc_x} (Å)")
        ax.set_ylabel(f"PC{pc_y} (Å)")
        ax.set_title(f"PCA projection: PC{pc_x} vs PC{pc_y}")
        ax.grid(True, alpha=0.25)
        fig.tight_layout()
        fig.savefig(out, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return {
            "success": True,
            "message": f"PCA projection plot saved to {out}",
            "output_file": out,
            "pc_x": pc_x,
            "pc_y": pc_y,
            "n_points": len(x),
        }
    except Exception as exc:
        logger.exception("PCA projection plot failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original_dir)


@tool
def calculate_free_energy_landscape(
    pca_projections_file: Optional[str] = None,
    topology_file: Optional[str] = None,
    trajectory_file: Optional[str] = None,
    pc_x: int = 1,
    pc_y: int = 2,
    bins: int = 50,
    temperature_k: float = 310.0,
    selection: str = "protein and name CA",
    n_components: int = 10,
    frame_interval: int = 1,
    output_plot: Optional[str] = None,
    output_grid: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build a free-energy landscape (FEL) from PCA projections: F = −kT ln P(PCx, PCy).

    Uses a 2D histogram of PC coordinates to estimate the probability density P,
    then converts to a relative free energy in kJ/mol (minimum set to 0).

    Provide either:
    - ``pca_projections_file`` from ``calculate_trajectory_pca``, **or**
    - ``topology_file`` + ``trajectory_file`` (PCA is run internally).

    Args:
        pca_projections_file: Existing ``pca_projections.dat`` (preferred).
        topology_file: Topology if PCA must be computed here.
        trajectory_file: Trajectory if PCA must be computed here.
        pc_x: PC for horizontal axis (1-based, default 1).
        pc_y: PC for vertical axis (1-based, default 2).
        bins: Histogram bins per axis (default 50).
        temperature_k: Temperature for kT (default 310 K).
        selection: Atom selection when running PCA inline.
        n_components: PCs to compute when running PCA inline.
        frame_interval: Frame stride when running PCA inline.
        output_plot: FEL PNG (default ``fel_pc{pc_x}_pc{pc_y}.png``).
        output_grid: CSV grid export (default ``fel_pc{pc_x}_pc{pc_y}_grid.csv``).
        working_dir: Output directory.

    Returns:
        Dict with FEL output paths and summary free-energy statistics.

    Standard outputs: ``fel_pc1_pc2.png``, ``fel_pc1_pc2_grid.csv``.
    """
    if not HAS_MATPLOTLIB:
        return {"success": False, "error": "matplotlib is required for FEL plots"}

    original_dir = None
    try:
        original_dir = _chdir_working(working_dir)

        if pca_projections_file and os.path.exists(pca_projections_file):
            loaded = load_pca_projections(pca_projections_file)
            if not loaded.get("success"):
                return loaded
            projections = loaded["projections"]
        elif topology_file and trajectory_file:
            pca_result = _run_trajectory_pca(
                topology_file,
                trajectory_file,
                selection=selection,
                n_components=max(n_components, max(pc_x, pc_y)),
                frame_interval=frame_interval,
            )
            if not pca_result.get("success"):
                return pca_result
            projections = pca_result["projections"]
            # Save projections for downstream reuse
            _write_pca_tables(
                projections,
                pca_result["variance"],
                pca_result["cumulative_variance"],
                pca_result["times_ps"],
            )
        else:
            return {
                "success": False,
                "error": (
                    "Provide pca_projections_file or both topology_file and trajectory_file"
                ),
            }

        ix, iy = int(pc_x) - 1, int(pc_y) - 1
        if ix < 0 or iy < 0 or ix >= projections.shape[1] or iy >= projections.shape[1]:
            return {
                "success": False,
                "error": f"PC indices {pc_x}/{pc_y} out of range",
            }

        fel = _compute_free_energy_grid(
            projections[:, ix],
            projections[:, iy],
            bins=bins,
            temperature_k=temperature_k,
        )
        if not fel.get("success"):
            return fel

        plot_out = output_plot or f"fel_pc{pc_x}_pc{pc_y}.png"
        grid_out = output_grid or f"fel_pc{pc_x}_pc{pc_y}_grid.csv"

        F = fel["free_energy"]
        X, Y = np.meshgrid(fel["x_centers"], fel["y_centers"])

        # Export grid (long format for scripts; also readable)
        with open(grid_out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow([f"PC{pc_x}", f"PC{pc_y}", "free_energy_kJ_mol", "probability"])
            for j in range(F.shape[0]):
                for i in range(F.shape[1]):
                    writer.writerow([
                        f"{fel['x_centers'][i]:.6f}",
                        f"{fel['y_centers'][j]:.6f}",
                        f"{F[j, i]:.6f}",
                        f"{fel['probability'][j, i]:.6e}",
                    ])

        fig, ax = plt.subplots(figsize=(7.5, 6))
        P = fel["probability"]
        F_plot = F.astype(float).copy()
        F_plot[P <= 0] = np.nan
        finite = F_plot[np.isfinite(F_plot)]
        if finite.size:
            F_plot = F_plot - float(np.nanmin(finite))
        levels, vmin, vmax = _fel_surface_levels(F_plot, P)
        cf = ax.contourf(
            X, Y, F_plot, levels=levels, cmap=FEL_BASIN_CMAP,
            vmin=vmin, vmax=vmax, extend="max",
        )
        iso = [lv for lv in FEL_ENERGY_CONTOUR_KJ if vmin < lv < vmax]
        if iso:
            ax.contour(X, Y, F_plot, levels=iso, colors="0.15", linewidths=0.45, alpha=0.55)
        ax.set_facecolor("white")
        fig.colorbar(cf, ax=ax, label="Relative free energy (kJ/mol)")
        ax.set_xlabel(f"PC{pc_x} (Å)")
        ax.set_ylabel(f"PC{pc_y} (Å)")
        ax.set_title(f"Free-energy landscape (T={temperature_k:.0f} K)")
        fig.tight_layout()
        fig.savefig(plot_out, dpi=150, bbox_inches="tight")
        plt.close(fig)

        if working_dir:
            try:
                append_analysis_summary(
                    working_dir=working_dir,
                    analysis_type="FreeEnergyLandscape",
                    statistics={
                        "PC_x": pc_x,
                        "PC_y": pc_y,
                        "temperature_K": temperature_k,
                        "bins": bins,
                        "min_free_energy_kJ_mol": float(np.nanmin(F)),
                        "max_free_energy_kJ_mol": float(np.nanmax(F)),
                    },
                    files={"plot": plot_out, "grid": grid_out},
                    metadata={"pca_projections_file": pca_projections_file},
                )
            except Exception as exc:
                logger.warning("Failed to write FEL summary: %s", exc)

        return {
            "success": True,
            "message": (
                f"Free-energy landscape saved: {plot_out} "
                f"(PC{pc_x} vs PC{pc_y}, T={temperature_k} K)"
            ),
            "output_plot": plot_out,
            "output_grid": grid_out,
            "temperature_k": temperature_k,
            "pc_x": pc_x,
            "pc_y": pc_y,
            "min_free_energy_kJ_mol": float(np.nanmin(F)),
            "max_free_energy_kJ_mol": float(np.nanmax(F)),
        }
    except Exception as exc:
        logger.exception("Free-energy landscape failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original_dir)


# ── FEL landscape feature extraction (classification metrics) ─────────────────

DEFAULT_MIN_BASIN_POPULATION = 0.05
# Blue (low ΔF) → teal/amber → light coral (high ΔF).
# Avoid dark crimson highs (wash out basin contrast); no white midtones (white = unsampled).
if LinearSegmentedColormap is not None:
    FEL_BASIN_CMAP = LinearSegmentedColormap.from_list(
        "fel_blue_amber_coral",
        [
            "#0B3D91",  # deep blue — global/basin minima
            "#1D6BB8",
            "#3D9BD9",  # clear mid-basin blue
            "#5BBFBF",  # teal hinge (still cool)
            "#A8D08D",  # soft green
            "#F4D35E",  # warm amber
            "#F5A26B",  # peach
            "#F08080",  # light coral — high free energy
        ],
        N=256,
    )
else:
    FEL_BASIN_CMAP = "turbo"
FEL_BASIN_MARKER_COLOR = "#111111"  # black — local basin minima
FEL_GLOBAL_MIN_MARKER_COLOR = "#7B1FA2"  # purple — global free-energy minimum
FEL_SURFACE_VMAX_PAD_KJ = 8.0
FEL_SURFACE_VMAX_FLOOR_KJ = 18.0
FEL_ENERGY_CONTOUR_KJ = (5.0, 10.0, 15.0, 20.0)


def _fel_surface_levels(
    F: np.ndarray,
    P: np.ndarray,
) -> Tuple[np.ndarray, float, float]:
    """Contour levels for FEL plots; unsampled bins should be NaN in ``F``."""
    if np.any(np.isnan(F)):
        sampled = F[np.isfinite(F)]
    else:
        sampled = F[P > 0]
    if sampled.size == 0:
        sampled = F[np.isfinite(F)]
    vmin = 0.0
    p98 = float(np.percentile(sampled, 98)) if sampled.size else float(np.nanmax(F))
    vmax = max(p98 + FEL_SURFACE_VMAX_PAD_KJ, FEL_SURFACE_VMAX_FLOOR_KJ)
    vmax = min(vmax, float(np.nanmax(F)))
    levels = np.linspace(vmin, vmax, 24)
    return levels, vmin, vmax


def plot_fel_basins_on_axes(
    ax,
    *,
    x_centers: np.ndarray,
    y_centers: np.ndarray,
    free_energy: np.ndarray,
    probability: np.ndarray,
    basins: List[Dict[str, Any]],
    smooth_sigma: float = 1.0,
    pc_x: int = 1,
    pc_y: int = 2,
    title: Optional[str] = None,
    show_population_pct: bool = True,
    basin_marker_color: str = FEL_BASIN_MARKER_COLOR,
    global_min_marker_color: str = FEL_GLOBAL_MIN_MARKER_COLOR,
    global_min_basin_id: Optional[int] = None,
    annotation_fontsize: float = 9,
    marker_size: float = 16,
    cmap=None,
    label_placement: str = "auto",
):
    """
    Draw a masked FEL surface (blue minima → light coral highs) with basin markers.

    Only basins supplied in ``basins`` are annotated (expected: already ≥ cutoff).
    The global free-energy minimum basin is marked with a blue star; other basins
    use ``basin_marker_color`` (default black).

    ``label_placement`` controls annotation offsets:
      - ``"auto"``: staggered around the star (default)
      - ``"below"``: all labels under the star
      - ``"right"``: all labels to the right of the star
    """
    F = free_energy.astype(float)
    P = probability
    F_plot = F.copy()
    F_plot[P <= 0] = np.nan
    finite = F_plot[np.isfinite(F_plot)]
    if finite.size:
        F_plot = F_plot - float(np.nanmin(finite))

    X, Y = np.meshgrid(x_centers, y_centers)
    levels, vmin, vmax = _fel_surface_levels(F_plot, P)
    cf = ax.contourf(
        X,
        Y,
        F_plot,
        levels=levels,
        cmap=cmap if cmap is not None else FEL_BASIN_CMAP,
        vmin=vmin,
        vmax=vmax,
        extend="max",
        alpha=0.95,
    )

    finite = F_plot[np.isfinite(F_plot)]
    if finite.size:
        iso_levels = [lv for lv in FEL_ENERGY_CONTOUR_KJ if vmin < lv < vmax]
        if iso_levels:
            ax.contour(
                X,
                Y,
                F_plot,
                levels=iso_levels,
                colors="0.15",
                linewidths=0.45,
                alpha=0.55,
            )

    F_smooth = _smooth_fel_grid(F, smooth_sigma)
    minima = [(int(b["min_y"]), int(b["min_x"])) for b in basins]
    if minima:
        basin_labels = _assign_fel_basins(F_smooth, minima)
        basin_levels = sorted({int(x) for x in basin_labels.flat if x > 0})
        if basin_levels:
            ax.contour(
                X,
                Y,
                basin_labels,
                levels=basin_levels,
                colors="white",
                linewidths=1.8,
                alpha=0.95,
                zorder=4,
            )
            ax.contour(
                X,
                Y,
                basin_labels,
                levels=basin_levels,
                colors="black",
                linewidths=0.55,
                alpha=0.75,
                zorder=4,
            )

    # Resolve global-min basin id (lowest free_energy_min among supplied basins).
    gmin_id = global_min_basin_id
    if gmin_id is None and basins:
        energies = []
        for b in basins:
            try:
                energies.append(float(b.get("free_energy_min_kJ_mol")))
            except (TypeError, ValueError):
                energies.append(float("inf"))
        if any(np.isfinite(energies)):
            gmin_id = int(basins[int(np.argmin(energies))]["basin_id"])

    placement = (label_placement or "auto").strip().lower()
    if placement == "below":
        # All labels under the star (mild x-stagger to reduce collisions).
        below_offsets = (
            (0, -18),
            (-12, -18),
            (12, -18),
            (-18, -22),
            (18, -22),
            (0, -26),
            (-8, -26),
            (8, -26),
        )
    elif placement == "right":
        # All labels to the right of the star (mild y-stagger only).
        right_offsets = (
            (16, 0),
            (16, 8),
            (16, -8),
            (18, 14),
            (18, -14),
            (20, 4),
            (20, -4),
            (16, 18),
        )
    else:
        auto_offsets = (
            (14, 12),
            (-18, 12),
            (14, -16),
            (-18, -16),
            (0, 18),
            (20, 0),
            (-22, 0),
            (10, 20),
        )

    for b in basins:
        bx = float(x_centers[int(b["min_x"])])
        by = float(y_centers[int(b["min_y"])])
        bid = int(b["basin_id"])
        is_gmin = gmin_id is not None and bid == int(gmin_id)
        marker_color = global_min_marker_color if is_gmin else basin_marker_color
        msize = marker_size * (1.35 if is_gmin else 1.0)
        label = str(bid)
        if show_population_pct:
            label = f"{bid}, {100.0 * float(b.get('population', 0)):.0f}%"
        ax.plot(
            bx,
            by,
            marker="*",
            color=marker_color,
            markersize=msize,
            markeredgecolor="white",
            markeredgewidth=0.8,
            zorder=5,
            label="global min" if is_gmin else None,
        )
        if placement == "below":
            dx, dy = below_offsets[(bid - 1) % len(below_offsets)]
            ha, va = "center", "top"
        elif placement == "right":
            dx, dy = right_offsets[(bid - 1) % len(right_offsets)]
            ha, va = "left", "center"
        else:
            dx, dy = auto_offsets[(bid - 1) % len(auto_offsets)]
            ha, va = "center", "center"
        ax.annotate(
            label,
            (bx, by),
            textcoords="offset points",
            xytext=(dx, dy),
            fontsize=annotation_fontsize,
            fontweight="bold",
            color="0.15",
            ha=ha,
            va=va,
            bbox=dict(
                boxstyle="round,pad=0.28",
                facecolor="0.92",
                edgecolor="0.45",
                linewidth=0.7,
                alpha=0.92,
            ),
            arrowprops=dict(
                arrowstyle="-",
                color="0.45",
                lw=0.8,
                shrinkA=0,
                shrinkB=4,
            ),
            zorder=6,
        )

    ax.set_facecolor("white")
    ax.set_xlabel(f"PC{pc_x} (Å)")
    ax.set_ylabel(f"PC{pc_y} (Å)")
    if title:
        ax.set_title(title)
    return cf


def load_fel_grid_csv(path: str) -> Dict[str, Any]:
    """Load long-format FEL grid CSV written by ``calculate_free_energy_landscape``."""
    p = Path(path)
    if not p.is_file():
        return {"success": False, "error": f"FEL grid file not found: {path}"}

    xs: List[float] = []
    ys: List[float] = []
    fs: List[float] = []
    ps: List[float] = []

    with open(p, encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            return {"success": False, "error": f"Empty FEL grid CSV: {path}"}
        for row in reader:
            try:
                pc_cols = [c for c in reader.fieldnames if c.startswith("PC")]
                if len(pc_cols) >= 2:
                    xs.append(float(row[pc_cols[0]]))
                    ys.append(float(row[pc_cols[1]]))
                else:
                    xs.append(float(row.get("PC1", row.get("x", 0))))
                    ys.append(float(row.get("PC2", row.get("y", 0))))
                fs.append(float(row.get("free_energy_kJ_mol", row.get("F", 0))))
                ps.append(float(row.get("probability", row.get("P", 0))))
            except (TypeError, ValueError, KeyError):
                continue

    if not xs:
        return {"success": False, "error": f"No valid rows in FEL grid CSV: {path}"}

    x_unique = sorted(set(xs))
    y_unique = sorted(set(ys))
    nx, ny = len(x_unique), len(y_unique)
    F = np.full((ny, nx), np.nan, dtype=float)
    P = np.zeros((ny, nx), dtype=float)

    x_index = {v: i for i, v in enumerate(x_unique)}
    y_index = {v: i for i, v in enumerate(y_unique)}
    for x, y, f, prob in zip(xs, ys, fs, ps):
        j, i = y_index[y], x_index[x]
        F[j, i] = f
        P[j, i] = prob

    if np.isnan(F).any():
        F = np.nan_to_num(F, nan=np.nanmax(F[np.isfinite(F)]))

    return {
        "success": True,
        "free_energy": F,
        "probability": P,
        "x_centers": np.asarray(x_unique, dtype=float),
        "y_centers": np.asarray(y_unique, dtype=float),
        "path": str(p.resolve()),
    }


def _smooth_fel_grid(grid: np.ndarray, sigma: float) -> np.ndarray:
    from scipy.ndimage import gaussian_filter

    return gaussian_filter(grid, sigma=max(float(sigma), 0.0), mode="nearest")


def _find_fel_minima(
    F: np.ndarray,
    *,
    smooth_sigma: float = 1.0,
    min_prominence: float = 0.5,
    merge_distance: int = 2,
) -> Tuple[List[Tuple[int, int]], np.ndarray]:
    """Return (y, x) coordinates of significant local minima on the FEL grid."""
    from scipy.ndimage import maximum_filter, minimum_filter

    F_s = _smooth_fel_grid(F, smooth_sigma)
    f_range = float(np.nanmax(F_s) - np.nanmin(F_s))
    prominence = max(float(min_prominence), 0.08 * f_range)

    local_min = minimum_filter(F_s, size=3, mode="nearest")
    is_min = (F_s <= local_min + 1e-9) & np.isfinite(F_s)

    local_max = maximum_filter(F_s, size=7, mode="nearest")
    is_min &= (local_max - F_s) >= prominence

    coords = sorted(
        [(int(y), int(x)) for y, x in zip(*np.where(is_min))],
        key=lambda c: F_s[c],
    )

    merged: List[Tuple[int, int]] = []
    taken = set()
    for y, x in coords:
        if (y, x) in taken:
            continue
        merged.append((y, x))
        for y2, x2 in coords:
            if abs(y2 - y) <= merge_distance and abs(x2 - x) <= merge_distance:
                taken.add((y2, x2))

    return merged, F_s


def _assign_fel_basins(F: np.ndarray, minima: List[Tuple[int, int]]) -> np.ndarray:
    """Assign each grid cell to a basin via steepest descent to the nearest minimum."""
    h, w = F.shape
    if not minima:
        return np.zeros((h, w), dtype=int)

    min_map = {coord: idx + 1 for idx, coord in enumerate(minima)}
    labels = np.zeros((h, w), dtype=int)

    for j in range(h):
        for i in range(w):
            y, x = j, i
            seen = set()
            while (y, x) not in min_map:
                if (y, x) in seen:
                    break
                seen.add((y, x))
                best_y, best_x = y, x
                best_f = F[y, x]
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dy == 0 and dx == 0:
                            continue
                        ny, nx = y + dy, x + dx
                        if 0 <= ny < h and 0 <= nx < w and F[ny, nx] < best_f:
                            best_f = F[ny, nx]
                            best_y, best_x = ny, nx
                if best_y == y and best_x == x:
                    break
                y, x = best_y, best_x
            if (y, x) in min_map:
                labels[j, i] = min_map[(y, x)]
            else:
                # Plateau / ambiguous — nearest minimum by grid distance
                dists = [abs(y - my) + abs(x - mx) for my, mx in minima]
                labels[j, i] = int(np.argmin(dists)) + 1

    return labels


def _line_cells(y0: int, x0: int, y1: int, x1: int) -> List[Tuple[int, int]]:
    """Bresenham-like line between two grid points."""
    cells: List[Tuple[int, int]] = []
    dy = abs(y1 - y0)
    dx = abs(x1 - x0)
    sy = 1 if y0 < y1 else -1
    sx = 1 if x0 < x1 else -1
    err = dx - dy
    y, x = y0, x0
    while True:
        cells.append((y, x))
        if y == y1 and x == x1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x += sx
        if e2 < dx:
            err += dx
            y += sy
    return cells


def _inter_basin_barrier(
    F: np.ndarray,
    min_a: Tuple[int, int],
    min_b: Tuple[int, int],
) -> float:
    """Lowest maximum F along a straight grid path (saddle estimate)."""
    path = _line_cells(min_a[0], min_a[1], min_b[0], min_b[1])
    f_path = [F[y, x] for y, x in path if 0 <= y < F.shape[0] and 0 <= x < F.shape[1]]
    if not f_path:
        return 0.0
    saddle = float(max(f_path))
    base = min(F[min_a], F[min_b])
    return max(0.0, saddle - base)


def _watershed_ridge_barrier(
    F: np.ndarray,
    labels: np.ndarray,
    id_a: int,
    id_b: int,
    f_min_a: float,
    f_min_b: float,
) -> Optional[float]:
    """
    Barrier from the lowest shared watershed ridge between two labeled basins.

    For every 8-neighbour contact between cells of ``id_a`` and ``id_b``, take
    max(F_a, F_b); the saddle is the minimum of those values. Barrier height is
    saddle − min(F_min_a, F_min_b). Returns None if the basins do not touch.
    """
    h, w = F.shape
    saddle = None
    for y in range(h):
        for x in range(w):
            if int(labels[y, x]) != int(id_a):
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if not (0 <= ny < h and 0 <= nx < w):
                        continue
                    if int(labels[ny, nx]) != int(id_b):
                        continue
                    cross = float(max(F[y, x], F[ny, nx]))
                    if saddle is None or cross < saddle:
                        saddle = cross
    if saddle is None:
        return None
    base = float(min(f_min_a, f_min_b))
    return max(0.0, float(saddle) - base)


def _basin_pair_barrier(
    F: np.ndarray,
    labels: np.ndarray,
    basin_a: Dict[str, Any],
    basin_b: Dict[str, Any],
) -> Tuple[float, str]:
    """Prefer watershed-ridge barrier; fall back to straight-line path."""
    ridge = _watershed_ridge_barrier(
        F,
        labels,
        int(basin_a["basin_id"]),
        int(basin_b["basin_id"]),
        float(basin_a["free_energy_min_kJ_mol"]),
        float(basin_b["free_energy_min_kJ_mol"]),
    )
    if ridge is not None:
        return float(ridge), "watershed_ridge"
    line = _inter_basin_barrier(
        F,
        (int(basin_a["min_y"]), int(basin_a["min_x"])),
        (int(basin_b["min_y"]), int(basin_b["min_x"])),
    )
    return float(line), "straight_line"


def _merge_basins_barrier_aware(
    F: np.ndarray,
    P: np.ndarray,
    basins: List[Dict[str, Any]],
    *,
    merge_barrier_kJ_mol: float,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], np.ndarray]:
    """
    Iteratively merge basin pairs whose barrier is below ``merge_barrier_kJ_mol``.

    After merges, re-assign the grid from surviving minima and refresh populations
    so plotted watersheds match the reported basin list.
    """
    if len(basins) <= 1 or merge_barrier_kJ_mol is None:
        minima = [(int(b["min_y"]), int(b["min_x"])) for b in basins]
        labels = _assign_fel_basins(F, minima) if minima else np.zeros(F.shape, dtype=int)
        return basins, [], labels

    threshold = float(merge_barrier_kJ_mol)
    current = [dict(b) for b in basins]
    merge_log: List[Dict[str, Any]] = []
    total_p = float(P.sum()) or 1.0

    # Working labels from current minima (ids match basin_id)
    def _relabel(bas: List[Dict[str, Any]]) -> np.ndarray:
        for i, b in enumerate(bas, start=1):
            b["basin_id"] = i
        mins = [(int(b["min_y"]), int(b["min_x"])) for b in bas]
        return _assign_fel_basins(F, mins)

    labels = _relabel(current)

    while len(current) > 1:
        best = None  # (barrier, method, i, j)
        for i in range(len(current)):
            for j in range(i + 1, len(current)):
                barrier, method = _basin_pair_barrier(
                    F, labels, current[i], current[j]
                )
                if best is None or barrier < best[0]:
                    best = (barrier, method, i, j)
        if best is None or best[0] >= threshold:
            break

        barrier, method, i, j = best
        # Keep the deeper minimum as representative; absorb the other.
        if float(current[i]["free_energy_min_kJ_mol"]) <= float(
            current[j]["free_energy_min_kJ_mol"]
        ):
            keep, drop = i, j
        else:
            keep, drop = j, i

        kept = current[keep]
        dropped = current[drop]
        merge_log.append({
            "kept_basin_min_yx": [int(kept["min_y"]), int(kept["min_x"])],
            "dropped_basin_min_yx": [int(dropped["min_y"]), int(dropped["min_x"])],
            "barrier_kJ_mol": float(barrier),
            "barrier_method": method,
            "threshold_kJ_mol": threshold,
            "kept_F_min": float(kept["free_energy_min_kJ_mol"]),
            "dropped_F_min": float(dropped["free_energy_min_kJ_mol"]),
            "population_before_kept": float(kept["population"]),
            "population_before_dropped": float(dropped["population"]),
        })
        current.pop(drop)
        labels = _relabel(current)

        # Refresh populations / depths from reassigned labels
        refreshed: List[Dict[str, Any]] = []
        for b in current:
            bid = int(b["basin_id"])
            mask = labels == bid
            my, mx = int(b["min_y"]), int(b["min_x"])
            f_min = float(F[my, mx])
            f_max_in = float(np.max(F[mask])) if mask.any() else f_min
            refreshed.append({
                "basin_id": bid,
                "min_y": my,
                "min_x": mx,
                "free_energy_min_kJ_mol": f_min,
                "population": float(P[mask].sum() / total_p),
                "basin_depth_kJ_mol": f_max_in - f_min,
                "area_fraction": float(mask.sum()) / float(F.size),
                "n_grid_cells": int(mask.sum()),
            })
        current = refreshed

    return current, merge_log, labels


def analyze_fel_landscape_core(
    F: np.ndarray,
    P: np.ndarray,
    *,
    smooth_sigma: float = 1.0,
    min_basin_population: float = DEFAULT_MIN_BASIN_POPULATION,
    min_prominence_kj_mol: float = 0.5,
    merge_barrier_kJ_mol: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Extract classification features from a 2D FEL grid.

    **Basin detection algorithm (reported as ``n_basins``, max 8):**

    1. **Smooth** the free-energy grid (Gaussian σ = ``smooth_sigma``).
    2. **Find local minima** on the smoothed surface (3×3 neighbourhood) with
       minimum **prominence** (≥ ``min_prominence_kj_mol`` or 8% of F range).
    3. **Assign basins** by steepest descent from each grid cell to the nearest
       minimum; compute **population** pᵢ = Σ P(cell) per basin.
    4. **Filter & merge:** drop basins with population < ``min_basin_population``
       (default 5%); iteratively merge the smallest basin into the largest until at most
       **8 basins** remain (or all meet the population threshold).
    5. **Optional barrier-aware merge:** if ``merge_barrier_kJ_mol`` is set, merge
       pairs whose watershed-ridge barrier is below that threshold (continuous
       low-energy valleys → one basin). Re-assign labels from surviving minima.
    6. **Label basins:** assign ``basin_id`` 1…n by **population** (highest = 1).

    Only these final merged basins appear in ``fel_basins.png`` and in
    ``n_basins`` / ``landscape_entropy`` (S = −Σ pᵢ ln pᵢ).

    Metrics:
      - basins: per-basin population, depth, area
      - barriers: inter-basin saddle heights (kJ/mol above lower minimum)
      - major_basin_population: largest basin occupancy fraction
      - delta_F_major_minus_global_kJ_mol: F(major-population basin) − F(global
        minimum among kept basins); 0 when they coincide
    """
    minima, F_smooth = _find_fel_minima(
        F,
        smooth_sigma=smooth_sigma,
        min_prominence=min_prominence_kj_mol,
    )
    if not minima:
        # Single basin — treat global minimum as one minimum
        gy, gx = np.unravel_index(int(np.argmin(F_smooth)), F_smooth.shape)
        minima = [(int(gy), int(gx))]

    labels = _assign_fel_basins(F_smooth, minima)
    total_p = float(P.sum()) or 1.0

    basins: List[Dict[str, Any]] = []
    for idx, (my, mx) in enumerate(minima):
        bid = idx + 1
        mask = labels == bid
        pop = float(P[mask].sum() / total_p)
        if pop < float(min_basin_population):
            continue
        f_min = float(F_smooth[my, mx])
        f_max_in = float(np.max(F_smooth[mask])) if mask.any() else f_min
        depth = f_max_in - f_min
        area_fraction = float(mask.sum()) / float(F.size)
        basins.append({
            "basin_id": bid,
            "min_y": my,
            "min_x": mx,
            "free_energy_min_kJ_mol": f_min,
            "population": pop,
            "basin_depth_kJ_mol": depth,
            "area_fraction": area_fraction,
            "n_grid_cells": int(mask.sum()),
        })

    if not basins:
        # Keep at least the deepest minimum
        my, mx = minima[0]
        mask = labels == 1
        basins.append({
            "basin_id": 1,
            "min_y": my,
            "min_x": mx,
            "free_energy_min_kJ_mol": float(F_smooth[my, mx]),
            "population": float(P[mask].sum() / total_p),
            "basin_depth_kJ_mol": float(np.max(F_smooth[mask]) - F_smooth[my, mx]),
            "area_fraction": float(mask.sum()) / float(F.size),
            "n_grid_cells": int(mask.sum()),
        })

    # Re-label basin_id sequentially after population filter
    for new_id, b in enumerate(basins, start=1):
        b["basin_id"] = new_id

    n_minima_detected = len(basins)

    # Merge tiny basins into the major basin until population threshold is met
    max_basins = 8
    while len(basins) > 1:
        pops = [b["population"] for b in basins]
        if len(basins) <= max_basins and min(pops) >= float(min_basin_population):
            break
        smallest = int(np.argmin(pops))
        if pops[smallest] >= float(min_basin_population) and len(basins) <= max_basins:
            break
        major = int(np.argmax(pops))
        if smallest == major:
            break
        basins[major]["population"] += basins[smallest]["population"]
        basins[major]["area_fraction"] += basins[smallest]["area_fraction"]
        basins[major]["n_grid_cells"] += basins[smallest]["n_grid_cells"]
        basins[major]["basin_depth_kJ_mol"] = max(
            basins[major]["basin_depth_kJ_mol"],
            basins[smallest]["basin_depth_kJ_mol"],
        )
        basins.pop(smallest)
        for new_id, b in enumerate(basins, start=1):
            b["basin_id"] = new_id

    n_basins_before_barrier_merge = len(basins)
    barrier_merge_log: List[Dict[str, Any]] = []
    if merge_barrier_kJ_mol is not None and len(basins) > 1:
        basins, barrier_merge_log, _labels_merged = _merge_basins_barrier_aware(
            F_smooth,
            P,
            basins,
            merge_barrier_kJ_mol=float(merge_barrier_kJ_mol),
        )
        # Re-rank and refresh populations from surviving minima only.
        basins.sort(
            key=lambda b: (
                -float(b["population"]),
                float(b["free_energy_min_kJ_mol"]),
            ),
        )
        for new_id, b in enumerate(basins, start=1):
            b["basin_id"] = new_id
        final_minima = [(int(b["min_y"]), int(b["min_x"])) for b in basins]
        final_labels = _assign_fel_basins(F_smooth, final_minima)
        total_p = float(P.sum()) or 1.0
        for b in basins:
            mask = final_labels == int(b["basin_id"])
            my, mx = int(b["min_y"]), int(b["min_x"])
            f_min = float(F_smooth[my, mx])
            b["free_energy_min_kJ_mol"] = f_min
            b["population"] = float(P[mask].sum() / total_p)
            b["n_grid_cells"] = int(mask.sum())
            b["area_fraction"] = float(mask.sum()) / float(F.size)
            b["basin_depth_kJ_mol"] = (
                float(np.max(F_smooth[mask]) - f_min) if mask.any() else 0.0
            )
        basins.sort(
            key=lambda b: (
                -float(b["population"]),
                float(b["free_energy_min_kJ_mol"]),
            ),
        )
        for new_id, b in enumerate(basins, start=1):
            b["basin_id"] = new_id
        final_minima = [(int(b["min_y"]), int(b["min_x"])) for b in basins]
        final_labels = _assign_fel_basins(F_smooth, final_minima)
        for b in basins:
            mask = final_labels == int(b["basin_id"])
            b["population"] = float(P[mask].sum() / total_p)
            b["n_grid_cells"] = int(mask.sum())
            b["area_fraction"] = float(mask.sum()) / float(F.size)
    else:
        # Legacy path: rank by population; do not re-watershed.
        basins.sort(
            key=lambda b: (
                -float(b["population"]),
                float(b["free_energy_min_kJ_mol"]),
            ),
        )
        for new_id, b in enumerate(basins, start=1):
            b["basin_id"] = new_id
        final_minima = [(int(b["min_y"]), int(b["min_x"])) for b in basins]
        final_labels = _assign_fel_basins(F_smooth, final_minima)

    populations = np.asarray([b["population"] for b in basins], dtype=float)
    populations = populations / max(populations.sum(), 1e-12)
    landscape_entropy = float(-np.sum(populations * np.log(populations + 1e-12)))

    # Grid-level entropy (conformational spread in PC space)
    p_flat = P.ravel()
    p_flat = p_flat[p_flat > 0]
    grid_entropy = float(-np.sum(p_flat * np.log(p_flat + 1e-12)))

    major_idx = int(np.argmax(populations))
    major_basin = basins[major_idx]
    global_idx = int(np.argmin([float(b["free_energy_min_kJ_mol"]) for b in basins]))
    global_min_basin = basins[global_idx]
    # ΔF ≥ 0: free-energy offset of the most-populated basin above the deepest
    # kept basin (0 when major population basin is also the global minimum).
    delta_f_major_minus_global = float(
        float(major_basin["free_energy_min_kJ_mol"])
        - float(global_min_basin["free_energy_min_kJ_mol"])
    )

    barriers: List[Dict[str, Any]] = []
    for i in range(len(basins)):
        for j in range(i + 1, len(basins)):
            h_ij, method = _basin_pair_barrier(
                F_smooth, final_labels, basins[i], basins[j]
            )
            barriers.append({
                "basin_a": int(basins[i]["basin_id"]),
                "basin_b": int(basins[j]["basin_id"]),
                "barrier_height_kJ_mol": h_ij,
                "barrier_method": method,
            })

    max_barrier = max((b["barrier_height_kJ_mol"] for b in barriers), default=0.0)
    mean_depth = float(np.mean([b["basin_depth_kJ_mol"] for b in basins]))

    return {
        "success": True,
        "n_basins": len(basins),
        "n_minima": len(basins),  # backward-compatible alias
        "n_minima_detected": n_minima_detected,
        "n_basins_before_barrier_merge": n_basins_before_barrier_merge,
        "merge_barrier_kJ_mol": (
            float(merge_barrier_kJ_mol) if merge_barrier_kJ_mol is not None else None
        ),
        "barrier_merge_log": barrier_merge_log,
        "landscape_entropy": landscape_entropy,
        "grid_entropy": grid_entropy,
        "major_basin_population": float(major_basin["population"]),
        "major_basin_id": int(major_basin["basin_id"]),
        "global_min_basin_id": int(global_min_basin["basin_id"]),
        "global_min_free_energy_kJ_mol": float(
            global_min_basin["free_energy_min_kJ_mol"]
        ),
        "major_basin_free_energy_kJ_mol": float(
            major_basin["free_energy_min_kJ_mol"]
        ),
        "delta_F_major_minus_global_kJ_mol": delta_f_major_minus_global,
        "max_barrier_height_kJ_mol": float(max_barrier),
        "mean_basin_depth_kJ_mol": mean_depth,
        "basins": basins,
        "barriers": barriers,
    }


def _write_fel_feature_tables(
    features: Dict[str, Any],
    *,
    output_json: str,
    output_csv: str,
    output_basins_csv: str,
) -> None:
    summary = {
        k: features[k]
        for k in (
            "n_minima",
            "landscape_entropy",
            "grid_entropy",
            "major_basin_population",
            "major_basin_id",
            "global_min_basin_id",
            "global_min_free_energy_kJ_mol",
            "major_basin_free_energy_kJ_mol",
            "delta_F_major_minus_global_kJ_mol",
            "max_barrier_height_kJ_mol",
            "mean_basin_depth_kJ_mol",
        )
        if k in features
    }
    summary["basins"] = features.get("basins", [])
    summary["barriers"] = features.get("barriers", [])

    with open(output_json, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    with open(output_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "n_minima",
            "landscape_entropy",
            "grid_entropy",
            "major_basin_population",
            "major_basin_id",
            "global_min_basin_id",
            "delta_F_major_minus_global_kJ_mol",
            "max_barrier_height_kJ_mol",
            "mean_basin_depth_kJ_mol",
        ])
        writer.writerow([
            summary.get("n_minima"),
            f"{summary.get('landscape_entropy', 0):.6f}",
            f"{summary.get('grid_entropy', 0):.6f}",
            f"{summary.get('major_basin_population', 0):.6f}",
            summary.get("major_basin_id"),
            summary.get("global_min_basin_id"),
            f"{summary.get('delta_F_major_minus_global_kJ_mol', 0):.6f}",
            f"{summary.get('max_barrier_height_kJ_mol', 0):.6f}",
            f"{summary.get('mean_basin_depth_kJ_mol', 0):.6f}",
        ])

    with open(output_basins_csv, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "basin_id",
            "population",
            "basin_depth_kJ_mol",
            "area_fraction",
            "free_energy_min_kJ_mol",
            "n_grid_cells",
        ])
        for b in features.get("basins", []):
            writer.writerow([
                b["basin_id"],
                f"{b['population']:.6f}",
                f"{b['basin_depth_kJ_mol']:.6f}",
                f"{b['area_fraction']:.6f}",
                f"{b['free_energy_min_kJ_mol']:.6f}",
                b["n_grid_cells"],
            ])


@tool
def analyze_fel_landscape_features(
    fel_grid_file: Optional[str] = None,
    pca_projections_file: Optional[str] = None,
    topology_file: Optional[str] = None,
    trajectory_file: Optional[str] = None,
    pc_x: int = 1,
    pc_y: int = 2,
    bins: int = 50,
    temperature_k: float = 310.0,
    smooth_sigma: float = 1.0,
    min_basin_population: float = DEFAULT_MIN_BASIN_POPULATION,
    min_prominence_kj_mol: float = 0.5,
    output_json: Optional[str] = None,
    output_csv: Optional[str] = None,
    output_basins_csv: Optional[str] = None,
    output_plot: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Extract FEL classification features for conformational diversity analysis.

    Computes from a PC1/PC2 free-energy landscape:
      - **Number of minima** (significant basins)
      - **Basin depth** (kJ/mol below basin rim)
      - **Basin area** (grid-cell fraction and population)
      - **Barrier heights** between basin pairs
      - **Major basin population** (largest basin occupancy)
      - **Landscape entropy** S = −Σ p_i ln(p_i) over basin populations
        (higher S → more conformational diversity)

    Run after ``calculate_free_energy_landscape``. Input priority:
    1. ``fel_grid_file`` (``fel_pc1_pc2_grid.csv``), or
    2. ``pca_projections_file``, or
    3. ``topology_file`` + ``trajectory_file`` (rebuilds FEL).

    Args:
        fel_grid_file (optional): Existing FEL grid CSV (preferred input).
        pca_projections_file (optional): PCA projections file to rebuild FEL.
        topology_file (optional): Topology for inline PCA/FEL rebuild.
        trajectory_file (optional): Trajectory for inline PCA/FEL rebuild.
        pc_x (optional): Principal component index for x axis (1-based).
        pc_y (optional): Principal component index for y axis (1-based).
        bins (optional): Number of 2D histogram bins per axis.
        temperature_k (optional): Temperature in Kelvin used for FEL conversion.
        smooth_sigma (optional): Gaussian smoothing sigma for basin detection.
        min_basin_population (optional): Minimum basin population fraction (default 5%).
        min_prominence_kj_mol (optional): Minimum basin prominence in kJ/mol.
        output_json (optional): Output JSON file for FEL feature summary.
        output_csv (optional): Output one-row CSV summary file.
        output_basins_csv (optional): Output per-basin CSV file.
        output_plot (optional): Output PNG with basin annotations.
        working_dir (optional): Output working directory.

    Returns:
        Dict with FEL feature statistics and output artifact paths.

    Standard outputs: ``fel_features.json``, ``fel_features.csv``, ``fel_basins.csv``.
    Optional: ``fel_basins.png`` when ``output_plot`` is set.
    """
    original_dir = None
    try:
        original_dir = _chdir_working(working_dir)

        grid_file = fel_grid_file or "fel_pc1_pc2_grid.csv"
        if os.path.isfile(grid_file):
            loaded = load_fel_grid_csv(grid_file)
        elif pca_projections_file and os.path.exists(pca_projections_file):
            proj = load_pca_projections(pca_projections_file)
            if not proj.get("success"):
                return proj
            ix, iy = int(pc_x) - 1, int(pc_y) - 1
            loaded = _compute_free_energy_grid(
                proj["projections"][:, ix],
                proj["projections"][:, iy],
                bins=bins,
                temperature_k=temperature_k,
            )
        elif topology_file and trajectory_file:
            pca_result = _run_trajectory_pca(
                topology_file,
                trajectory_file,
                n_components=max(10, max(pc_x, pc_y)),
                frame_interval=1,
            )
            if not pca_result.get("success"):
                return pca_result
            ix, iy = int(pc_x) - 1, int(pc_y) - 1
            loaded = _compute_free_energy_grid(
                pca_result["projections"][:, ix],
                pca_result["projections"][:, iy],
                bins=bins,
                temperature_k=temperature_k,
            )
        else:
            return {
                "success": False,
                "error": (
                    "Provide fel_grid_file, pca_projections_file, or "
                    "topology_file + trajectory_file"
                ),
            }

        if not loaded.get("success"):
            return loaded

        features = analyze_fel_landscape_core(
            loaded["free_energy"],
            loaded["probability"],
            smooth_sigma=smooth_sigma,
            min_basin_population=min_basin_population,
            min_prominence_kj_mol=min_prominence_kj_mol,
        )
        if not features.get("success"):
            return features

        json_out = output_json or "fel_features.json"
        csv_out = output_csv or "fel_features.csv"
        basins_out = output_basins_csv or "fel_basins.csv"
        plot_out = output_plot if output_plot is not None else "fel_basins.png"
        _write_fel_feature_tables(
            features,
            output_json=json_out,
            output_csv=csv_out,
            output_basins_csv=basins_out,
        )

        if plot_out and HAS_MATPLOTLIB:
            fig, ax = plt.subplots(figsize=(8, 6.5))
            cf = plot_fel_basins_on_axes(
                ax=ax,
                x_centers=loaded["x_centers"],
                y_centers=loaded["y_centers"],
                free_energy=loaded["free_energy"],
                probability=loaded["probability"],
                basins=features["basins"],
                smooth_sigma=smooth_sigma,
                pc_x=pc_x,
                pc_y=pc_y,
                title=(
                    f"FEL basins (n={features.get('n_basins', features['n_minima'])}, "
                    f"S={features['landscape_entropy']:.2f})"
                ),
            )
            fig.colorbar(cf, ax=ax, label="Relative free energy (kJ/mol)")
            fig.tight_layout()
            fig.savefig(plot_out, dpi=150, bbox_inches="tight")
            plt.close(fig)

        if working_dir:
            try:
                append_analysis_summary(
                    working_dir=working_dir,
                    analysis_type="FELFeatures",
                    statistics={
                        "n_minima": features["n_minima"],
                        "landscape_entropy": features["landscape_entropy"],
                        "major_basin_population": features["major_basin_population"],
                        "max_barrier_height_kJ_mol": features["max_barrier_height_kJ_mol"],
                    },
                    files={
                        "features_json": json_out,
                        "features_csv": csv_out,
                        "basins_csv": basins_out,
                        **({"plot": plot_out} if plot_out and HAS_MATPLOTLIB else {}),
                    },
                    metadata={"fel_grid_file": grid_file},
                )
            except Exception as exc:
                logger.warning("Failed to write FEL features summary: %s", exc)

        msg = (
            f"FEL features: {features['n_minima']} minima, "
            f"S={features['landscape_entropy']:.3f}, "
            f"major basin={features['major_basin_population'] * 100:.1f}%"
        )
        return {
            "success": True,
            "message": msg,
            **{k: features[k] for k in (
                "n_minima",
                "n_minima_detected",
                "landscape_entropy",
                "grid_entropy",
                "major_basin_population",
                "major_basin_id",
                "max_barrier_height_kJ_mol",
                "mean_basin_depth_kJ_mol",
            )},
            "basins": features["basins"],
            "barriers": features["barriers"],
            "output_json": json_out,
            "output_csv": csv_out,
            "output_basins_csv": basins_out,
            "output_plot": plot_out if (plot_out and HAS_MATPLOTLIB) else None,
        }
    except Exception as exc:
        logger.exception("FEL feature extraction failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original_dir)


@tool
def collect_fel_features_table(
    base_directory: str,
    output_file: str = "fel_classification_features.csv",
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Collect per-simulation FEL classification features into one comparison table.

    Scans ``{base_directory}/{label}/analysis/fel_features.json`` for each
    simulation subdirectory and writes a CSV suitable for clustering or
    supervised classification across many protein–ATP systems.

    Run after all per-simulation ``analyze_fel_landscape_features`` steps complete.

    Args:
        base_directory: Multi-simulation root (e.g. ``agenticB5R1/``).
        output_file: Combined CSV path (default ``fel_classification_features.csv``).
        working_dir: Directory for the output file (default: ``base_directory/analysis/``).

    Standard output: ``{base}/analysis/fel_classification_features.csv``.
    """
    original_dir = None
    try:
        original_dir = _chdir_working(working_dir)
        base = Path(base_directory).resolve()
        if not base.is_dir():
            return {"success": False, "error": f"Base directory not found: {base}"}

        rows: List[Dict[str, Any]] = []
        for child in sorted(base.iterdir()):
            if not child.is_dir() or child.name in ("analysis", "reporter", "supervisor", "planner"):
                continue
            feat_path = child / "analysis" / "fel_features.json"
            if not feat_path.is_file():
                continue
            with open(feat_path, encoding="utf-8") as fh:
                data = json.load(fh)
            rows.append({
                "label": child.name,
                "sim_directory": str(child),
                "n_minima": data.get("n_minima"),
                "landscape_entropy": data.get("landscape_entropy"),
                "grid_entropy": data.get("grid_entropy"),
                "major_basin_population": data.get("major_basin_population"),
                "major_basin_id": data.get("major_basin_id"),
                "max_barrier_height_kJ_mol": data.get("max_barrier_height_kJ_mol"),
                "mean_basin_depth_kJ_mol": data.get("mean_basin_depth_kJ_mol"),
            })

        if not rows:
            return {
                "success": False,
                "error": (
                    f"No fel_features.json found under {base}/*/analysis/. "
                    "Run analyze_fel_landscape_features per simulation first."
                ),
            }

        out_path = Path(output_file)
        if not out_path.is_absolute():
            out_dir = Path(working_dir) if working_dir else base / "analysis"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / output_file

        fieldnames = list(rows[0].keys())
        with open(out_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return {
            "success": True,
            "message": f"Collected FEL features for {len(rows)} simulations → {out_path}",
            "output_file": str(out_path),
            "n_simulations": len(rows),
            "labels": [r["label"] for r in rows],
        }
    except Exception as exc:
        logger.exception("collect_fel_features_table failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original_dir)


def _resolve_topology_trajectory(
    topology_file: Optional[str],
    trajectory_file: Optional[str],
    sim_directory: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve topology and trajectory paths from explicit args or sim hpc/."""
    topo = topology_file
    traj = trajectory_file
    sim_root = Path(sim_directory).resolve() if sim_directory else None

    if topo:
        topo_path = Path(topo)
        if not topo_path.is_absolute() and sim_root is not None:
            for candidate in (sim_root / "hpc" / topo_path.name, sim_root / topo_path.name):
                if candidate.is_file():
                    topo = str(candidate.resolve())
                    break
    if traj:
        traj_path = Path(traj)
        if not traj_path.is_absolute() and sim_root is not None:
            for candidate in (sim_root / "hpc" / traj_path.name, sim_root / traj_path.name):
                if candidate.is_file():
                    traj = str(candidate.resolve())
                    break

    if topo and traj and os.path.isfile(topo) and os.path.isfile(traj):
        return topo, traj

    if not sim_root:
        return topo, traj

    hpc = sim_root / "hpc"
    if not hpc.is_dir():
        return topo, traj

    if not topo or not os.path.isfile(topo):
        for candidate in ("md.tpr", "md.gro", "processed.gro"):
            p = hpc / candidate
            if p.is_file():
                topo = str(p)
                break
    if not traj or not os.path.isfile(traj):
        for candidate in ("mdWrap.xtc", "md.xtc", "md.trr"):
            p = hpc / candidate
            if p.is_file():
                traj = str(p)
                break
    return topo, traj


def _write_structure_pdb(
    topology_file: str,
    trajectory_file: str,
    frame_index: int,
    output_path: Path,
) -> bool:
    """Extract one aligned frame (protein + ligand) as PDB."""
    if not HAS_MDA:
        return False

    try:
        u = mda.Universe(topology_file, trajectory_file)
        if u.trajectory.n_frames <= 0:
            return False

        frame_index = max(0, min(int(frame_index), u.trajectory.n_frames - 1))

        if u.trajectory.n_frames > 1:
            try:
                from MDAnalysis.analysis import align as _mda_align

                ref = mda.Universe(topology_file, trajectory_file)
                ref.trajectory[0]
                align_sel = (
                    "backbone" if u.select_atoms("backbone").n_atoms > 0 else "name CA"
                )
                if u.select_atoms(align_sel).n_atoms > 0:
                    _mda_align.AlignTraj(
                        u, ref, select=align_sel, in_memory=True
                    ).run()
            except Exception as exc:
                logger.debug("Basin PDB alignment skipped: %s", exc)

        u.trajectory[frame_index]

        bulk_ions = "resname NA NA+ CL CL- K K+ SOD CLA"
        water = "resname HOH WAT SOL TIP3 TIP4 SPC"
        sel_parts: List[str] = []
        if len(u.select_atoms("protein")) > 0:
            sel_parts.append("protein")
        if len(u.select_atoms("nucleic")) > 0:
            sel_parts.append("nucleic")
        other_sel = (
            f"not protein and not nucleic and not ({water}) and not ({bulk_ions})"
        )
        if len(u.select_atoms(other_sel)) > 0:
            sel_parts.append(f"({other_sel})")
        selection_str = " or ".join(sel_parts) if sel_parts else f"not ({water})"

        output_path.parent.mkdir(parents=True, exist_ok=True)
        u.select_atoms(selection_str).write(str(output_path))
        return output_path.is_file()
    except Exception as exc:
        logger.warning("Failed to write basin PDB %s: %s", output_path, exc)
        return False


def _representative_frames_for_basins(
    pc_x_vals: np.ndarray,
    pc_y_vals: np.ndarray,
    basins: List[Dict[str, Any]],
    x_centers: np.ndarray,
    y_centers: np.ndarray,
) -> Dict[int, int]:
    """Pick one trajectory row per basin — closest in PC space to basin minimum."""
    reps: Dict[int, int] = {}
    coords = np.column_stack([pc_x_vals, pc_y_vals])
    for basin in basins:
        bid = int(basin["basin_id"])
        target = np.array([
            float(x_centers[int(basin["min_x"])]),
            float(y_centers[int(basin["min_y"])]),
        ])
        dists = np.linalg.norm(coords - target, axis=1)
        reps[bid] = int(np.argmin(dists))
    return reps


@tool
def export_fel_basin_structures(
    topology_file: Optional[str] = None,
    trajectory_file: Optional[str] = None,
    fel_features_file: str = "fel_features.json",
    pca_projections_file: str = "pca_projections.dat",
    pc_x: int = 1,
    pc_y: int = 2,
    bins: int = 50,
    temperature_k: float = 310.0,
    output_dir: Optional[str] = None,
    manifest_file: str = "fel_basin_structures.csv",
    sim_directory: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Export representative PDB structures for each FEL basin (up to 8).

    After ``analyze_fel_landscape_features`` identifies basins on the PC1/PC2
    free-energy landscape, this tool maps each basin minimum back to the
    nearest trajectory frame in PCA space and writes one PDB per basin directly
    in ``{working_dir}/basin_XX.pdb`` (no subdirectory).

    Also writes ``fel_basin_structures.csv`` with basin_id, population,
    PC coordinates, frame index, time (ns), and PDB path — for highlighting
    transient conformations in a molecular viewer.

    Standard outputs: ``basin_01.pdb``, ``basin_02.pdb``, …, ``fel_basin_structures.csv``.
    """
    original_dir = None
    try:
        work_base = Path(working_dir).resolve() if working_dir else Path.cwd().resolve()
        if sim_directory is None:
            sim_directory = str(work_base.parent)

        feat_path = Path(fel_features_file)
        if not feat_path.is_absolute():
            feat_path = work_base / fel_features_file
        feat_path = feat_path.resolve()

        proj_path = Path(pca_projections_file)
        if not proj_path.is_absolute():
            proj_path = work_base / pca_projections_file
        proj_path = proj_path.resolve()

        topo, traj = _resolve_topology_trajectory(
            topology_file, trajectory_file, sim_directory=sim_directory
        )
        if topo:
            topo_path = Path(topo)
            if not topo_path.is_absolute():
                topo = str(topo_path.resolve())
        if traj:
            traj_path = Path(traj)
            if not traj_path.is_absolute():
                traj = str(traj_path.resolve())

        original_dir = _chdir_working(working_dir)

        if not feat_path.is_file():
            return {
                "success": False,
                "error": f"FEL features file not found: {feat_path}",
            }
        if not proj_path.is_file():
            return {
                "success": False,
                "error": f"PCA projections file not found: {proj_path}",
            }
        if not topo or not traj:
            return {
                "success": False,
                "error": (
                    "Topology and trajectory required. Pass topology_file + "
                    "trajectory_file or sim_directory with hpc/md.tpr and mdWrap.xtc."
                ),
            }
        if not HAS_MDA:
            return {"success": False, "error": "MDAnalysis is required for PDB export"}

        with open(feat_path, encoding="utf-8") as fh:
            fel_data = json.load(fh)
        basins = fel_data.get("basins") or []
        if not basins:
            return {"success": False, "error": "No basins found in fel_features.json"}

        loaded = load_pca_projections(str(proj_path))
        if not loaded.get("success"):
            return loaded

        ix, iy = int(pc_x) - 1, int(pc_y) - 1
        projections = loaded["projections"]
        if ix < 0 or iy < 0 or ix >= projections.shape[1] or iy >= projections.shape[1]:
            return {
                "success": False,
                "error": f"PC indices {pc_x}/{pc_y} out of range",
            }

        pc_x_vals = projections[:, ix]
        pc_y_vals = projections[:, iy]
        grid = _compute_free_energy_grid(
            pc_x_vals, pc_y_vals, bins=bins, temperature_k=temperature_k
        )
        if not grid.get("success"):
            return grid

        rep_indices = _representative_frames_for_basins(
            pc_x_vals,
            pc_y_vals,
            basins,
            grid["x_centers"],
            grid["y_centers"],
        )

        out_root = work_base
        if output_dir and output_dir not in (".", ""):
            out_root = work_base / output_dir
            out_root.mkdir(parents=True, exist_ok=True)
        manifest_rows: List[Dict[str, Any]] = []
        pdb_files: List[str] = []

        frame_indices = loaded.get("frame_indices")
        times_ns = loaded.get("times_ns")

        for basin in basins:
            bid = int(basin["basin_id"])
            traj_idx = rep_indices[bid]
            pdb_name = f"basin_{bid:02d}.pdb"
            pdb_path = out_root / pdb_name

            frame_idx = (
                int(frame_indices[traj_idx])
                if frame_indices is not None and len(frame_indices) > traj_idx
                else traj_idx
            )

            if not _write_structure_pdb(topo, traj, frame_idx, pdb_path):
                logger.warning("Failed to export PDB for basin %d", bid)
                continue

            pc1_val = float(pc_x_vals[traj_idx])
            pc2_val = float(pc_y_vals[traj_idx])
            time_ns = (
                float(times_ns[traj_idx])
                if times_ns is not None and len(times_ns) > traj_idx
                else None
            )
            target_pc1 = float(grid["x_centers"][int(basin["min_x"])])
            target_pc2 = float(grid["y_centers"][int(basin["min_y"])])
            dist_pc = float(
                np.hypot(pc1_val - target_pc1, pc2_val - target_pc2)
            )
            is_gmin = int(basin["basin_id"]) == int(
                fel_data.get("global_min_basin_id")
                or min(
                    basins,
                    key=lambda b: float(b.get("free_energy_min_kJ_mol", float("inf"))),
                )["basin_id"]
            )

            # Always write a dedicated global-min PDB (nearest frame to that basin min).
            if is_gmin:
                gmin_path = out_root / "basin_global_min.pdb"
                shutil.copy2(pdb_path, gmin_path)
                pdb_files.append(str(gmin_path.resolve()))

            manifest_rows.append({
                "basin_id": bid,
                "is_global_min": int(is_gmin),
                "population": basin.get("population"),
                "basin_depth_kJ_mol": basin.get("basin_depth_kJ_mol"),
                "free_energy_min_kJ_mol": basin.get("free_energy_min_kJ_mol"),
                "PC1_basin_min": target_pc1,
                "PC2_basin_min": target_pc2,
                "PC1_frame": pc1_val,
                "PC2_frame": pc2_val,
                "distance_to_basin_min_PC": dist_pc,
                "trajectory_row_index": traj_idx,
                "frame_index": frame_idx,
                "time_ns": time_ns,
                "pdb_file": str(pdb_path.resolve()),
            })
            pdb_files.append(str(pdb_path.resolve()))

        if not pdb_files:
            return {"success": False, "error": "No basin PDB files could be written"}

        manifest_path = Path(manifest_file)
        with open(manifest_path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(manifest_rows[0].keys()))
            writer.writeheader()
            writer.writerows(manifest_rows)

        if working_dir:
            try:
                append_analysis_summary(
                    working_dir=working_dir,
                    analysis_type="FELBasinStructures",
                    statistics={"n_basins": len(pdb_files)},
                    files={
                        "manifest_csv": str(manifest_path.resolve()),
                        "basin_pdbs": pdb_files,
                    },
                    metadata={"n_basins_detected": len(basins)},
                )
            except Exception as exc:
                logger.warning("Failed to write basin structure summary: %s", exc)

        return {
            "success": True,
            "message": (
                f"Exported {len(pdb_files)} basin representative structure(s) "
                f"→ {out_root}/"
            ),
            "n_basins": len(pdb_files),
            "pdb_files": pdb_files,
            "manifest_file": str(manifest_path.resolve()),
            "output_dir": str(out_root.resolve()),
        }
    except Exception as exc:
        logger.exception("export_fel_basin_structures failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original_dir)
