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
import logging
import os
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

    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
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
    """Merge canonical PCA/FEL defaults; user-goal overrides beat LLM plan params."""
    defaults = PCA_TOOL_DEFAULTS.get(tool_name)
    if not defaults:
        return kwargs
    merged = dict(kwargs)
    merged.update(defaults)
    merged.update(resolve_pca_overrides_from_goal(user_goal))
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
        levels = np.linspace(0, np.nanmax(F), 20)
        cf = ax.contourf(X, Y, F, levels=levels, cmap="viridis_r")
        ax.contour(X, Y, F, levels=levels[::2], colors="k", linewidths=0.35, alpha=0.4)
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
