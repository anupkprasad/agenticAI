"""General MD analysis tools (not paper-specific).

Ligand orientation, hydration occupancy, trajectory frame clustering,
and hydrogen-bond lifetimes. Pocket residue lists are optional.
"""

from __future__ import annotations

import csv
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

try:
    import numpy as np
    import MDAnalysis as mda
    from MDAnalysis.analysis import rms, hydrogenbonds

    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False


def _out_dir(working_dir: Optional[str], name: str) -> Path:
    base = Path(working_dir) if working_dir else Path(".")
    base.mkdir(parents=True, exist_ok=True)
    return base / name


def _pocket_selection(
    pocket_mapped: str = "",
    pocket_selection: str = "",
    label: str = "",
) -> str:
    if pocket_selection:
        return pocket_selection
    if not pocket_mapped:
        return ""
    path = Path(pocket_mapped)
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        from src.analysis.cross_sim_artifacts import pocket_resids_for_label

        resids = pocket_resids_for_label(data, label or "")
        if resids:
            return "protein and resid " + " ".join(str(r) for r in resids)
    except Exception:
        return ""
    return ""


@tool
def calculate_ligand_axis_angle(
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    pocket_selection: str = "",
    pocket_mapped: str = "",
    label: str = "",
    output_file: str = "pocket_axis_angle.csv",
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    """
    Ligand orientation vs the binding-site principal axis (0–90°).

    Use when the goal asks for orientation only, without the full
    pocket COM / SASA / contacts bundle.
    """
    if not HAS_DEPS:
        return {"success": False, "error": "MDAnalysis and numpy are required"}
    from src.analysis.consensus_pocket import _axis_angle_deg, _principal_axis

    pocket_sel = _pocket_selection(pocket_mapped, pocket_selection, label) or "protein"
    top, traj = Path(topology_file), Path(trajectory_file)
    if not top.is_file() or not traj.is_file():
        return {"success": False, "error": f"Missing files: {top}, {traj}"}
    try:
        u = mda.Universe(str(top), str(traj))
        lig = u.select_atoms(ligand_selection)
        pock = u.select_atoms(pocket_sel)
        if len(lig) < 3 or len(pock) < 3:
            return {
                "success": False,
                "error": f"Need ≥3 atoms in ligand ({len(lig)}) and pocket ({len(pock)})",
            }
        step = max(1, int(frame_interval or 1))
        rows: List[List[Any]] = []
        angles: List[float] = []
        for ts in u.trajectory[::step]:
            p_axis = _principal_axis(pock.positions)
            l_axis = _principal_axis(lig.positions)
            if p_axis is None or l_axis is None:
                continue
            ang = _axis_angle_deg(p_axis, l_axis)
            if ang is None:
                continue
            angles.append(float(ang))
            rows.append([float(ts.time), int(ts.frame), float(ang)])
        out = _out_dir(working_dir, output_file)
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["time_ps", "frame", "axis_angle_deg"])
            w.writerows(rows)
        summary = {
            "success": True,
            "n_frames": len(rows),
            "mean_axis_angle_deg": float(np.mean(angles)) if angles else None,
            "std_axis_angle_deg": float(np.std(angles)) if angles else None,
            "output_file": str(out),
            "pocket_selection": pocket_sel,
        }
        if working_dir:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Ligand_axis_angle",
                statistics={
                    k: summary[k]
                    for k in ("n_frames", "mean_axis_angle_deg", "std_axis_angle_deg")
                    if summary.get(k) is not None
                },
                files={"csv": str(out)},
            )
        return summary
    except Exception as exc:
        logger.exception("calculate_ligand_axis_angle failed")
        return {"success": False, "error": str(exc)}


@tool
def calculate_water_occupancy(
    topology_file: str,
    trajectory_file: str,
    pocket_selection: str = "",
    pocket_mapped: str = "",
    label: str = "",
    cutoff_A: float = 4.0,
    water_selection: str = "resname SOL TIP3 HOH WAT and name OW O",
    output_file: str = "water_occupancy.csv",
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    """
    Water occupancy in a shell around a site (default: pocket residues).

    Writes a per-frame water count and mean occupancy. ``pocket_mapped`` is
    optional — omit it to use ``pocket_selection`` or the protein.
    """
    if not HAS_DEPS:
        return {"success": False, "error": "MDAnalysis and numpy are required"}
    site = (
        _pocket_selection(pocket_mapped, pocket_selection, label)
        or pocket_selection
        or "protein"
    )
    top, traj = Path(topology_file), Path(trajectory_file)
    if not top.is_file() or not traj.is_file():
        return {"success": False, "error": f"Missing files: {top}, {traj}"}
    try:
        u = mda.Universe(str(top), str(traj))
        site_ag = u.select_atoms(site)
        waters = u.select_atoms(water_selection)
        if len(site_ag) == 0:
            return {"success": False, "error": f"Site selection matched 0 atoms: {site}"}
        if len(waters) == 0:
            return {"success": False, "error": f"No water oxygens matched: {water_selection}"}
        step = max(1, int(frame_interval or 1))
        counts: List[int] = []
        rows: List[List[Any]] = []
        for ts in u.trajectory[::step]:
            dist = mda.lib.distances.distance_array(
                waters.positions, site_ag.positions, box=u.dimensions
            )
            n = int(np.sum(np.any(dist <= float(cutoff_A), axis=1)))
            counts.append(n)
            rows.append([float(ts.time), int(ts.frame), n])
        out = _out_dir(working_dir, output_file)
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["time_ps", "frame", "n_waters"])
            w.writerows(rows)
        arr = np.asarray(counts, dtype=float)
        summary = {
            "success": True,
            "n_frames": len(counts),
            "cutoff_A": float(cutoff_A),
            "site_selection": site,
            "mean_n_waters": float(arr.mean()) if counts else 0.0,
            "std_n_waters": float(arr.std()) if counts else 0.0,
            "output_file": str(out),
        }
        if working_dir:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Water_occupancy",
                statistics={
                    "mean_n_waters": summary["mean_n_waters"],
                    "cutoff_A": cutoff_A,
                },
                files={"csv": str(out)},
            )
        return summary
    except Exception as exc:
        logger.exception("calculate_water_occupancy failed")
        return {"success": False, "error": str(exc)}


@tool
def cluster_trajectory_frames(
    topology_file: str,
    trajectory_file: str,
    selection: str = "protein and name CA",
    method: str = "gromos",
    rmsd_cutoff_A: float = 1.5,
    n_clusters: int = 0,
    output_dir: str = "trajectory_clusters",
    working_dir: Optional[str] = None,
    frame_interval: int = 5,
    max_frames: int = 400,
) -> Dict[str, Any]:
    """
    Cluster trajectory frames by Cα RMSD (GROMOS cutoff or k-means).

    Writes cluster assignments and one representative PDB per cluster.
    """
    if not HAS_DEPS:
        return {"success": False, "error": "MDAnalysis and numpy are required"}
    top, traj = Path(topology_file), Path(trajectory_file)
    if not top.is_file() or not traj.is_file():
        return {"success": False, "error": f"Missing files: {top}, {traj}"}
    try:
        u = mda.Universe(str(top), str(traj))
        ag = u.select_atoms(selection)
        if len(ag) < 3:
            return {"success": False, "error": f"Selection matched {len(ag)} atoms"}
        step = max(1, int(frame_interval or 1))
        frames = list(range(0, len(u.trajectory), step))
        if len(frames) > max_frames:
            stride = max(1, len(frames) // max_frames)
            frames = frames[::stride]
        coords = []
        times = []
        for idx in frames:
            u.trajectory[idx]
            coords.append(ag.positions.copy())
            times.append(float(u.trajectory.time))
        X = np.asarray(coords)
        n = len(X)
        # Pairwise RMSD after removing COM
        dmat = np.zeros((n, n), dtype=float)
        for i in range(n):
            a = X[i] - X[i].mean(axis=0)
            for j in range(i + 1, n):
                b = X[j] - X[j].mean(axis=0)
                # Kabsch
                h = a.T @ b
                u_svd, _, vt = np.linalg.svd(h)
                r = vt.T @ u_svd.T
                if np.linalg.det(r) < 0:
                    vt[-1] *= -1
                    r = vt.T @ u_svd.T
                rmsd = float(np.sqrt(((a @ r - b) ** 2).sum() / len(a)))
                dmat[i, j] = dmat[j, i] = rmsd

        method_l = (method or "gromos").strip().lower()
        if method_l in ("kmeans", "k-means") and n_clusters and n_clusters > 1:
            labels = _kmeans_from_dmat(dmat, int(n_clusters))
        else:
            labels = _gromos_cluster(dmat, float(rmsd_cutoff_A))

        out_dir = Path(working_dir) / output_dir if working_dir else Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        assign = out_dir / "cluster_assignments.csv"
        with assign.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["frame_index", "time_ps", "cluster_id"])
            for i, idx in enumerate(frames):
                w.writerow([idx, times[i], int(labels[i])])

        reps: Dict[int, str] = {}
        for cid in sorted(set(int(c) for c in labels)):
            members = [i for i, c in enumerate(labels) if int(c) == cid]
            # Medoid: smallest mean RMSD to other members
            best = min(members, key=lambda i: float(dmat[i, members].mean()))
            u.trajectory[frames[best]]
            pdb = out_dir / f"cluster_{cid:02d}_rep.pdb"
            ag.write(str(pdb))
            reps[cid] = str(pdb)

        summary = {
            "success": True,
            "method": "kmeans" if method_l.startswith("k") else "gromos",
            "n_frames_used": n,
            "n_clusters": len(set(int(c) for c in labels)),
            "rmsd_cutoff_A": float(rmsd_cutoff_A),
            "assignments_csv": str(assign),
            "representatives": reps,
        }
        (out_dir / "clusters.json").write_text(
            json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
        )
        if working_dir:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Trajectory_clusters",
                statistics={"n_clusters": summary["n_clusters"], "n_frames": n},
                files={"assignments": str(assign)},
            )
        return summary
    except Exception as exc:
        logger.exception("cluster_trajectory_frames failed")
        return {"success": False, "error": str(exc)}


def _gromos_cluster(dmat: np.ndarray, cutoff: float) -> List[int]:
    """GROMOS-style clustering: largest neighbor set within cutoff, iteratively."""
    n = dmat.shape[0]
    remaining = set(range(n))
    labels = [-1] * n
    cid = 1
    while remaining:
        best = max(
            remaining,
            key=lambda i: sum(1 for j in remaining if dmat[i, j] <= cutoff),
        )
        members = [j for j in remaining if dmat[best, j] <= cutoff]
        if not members:
            members = [best]
        for j in members:
            labels[j] = cid
            remaining.discard(j)
        cid += 1
    return labels


def _kmeans_from_dmat(dmat: np.ndarray, k: int) -> List[int]:
    """Classical MDS → k-means on the first few embedding axes."""
    n = dmat.shape[0]
    k = max(2, min(int(k), n))
    d2 = dmat ** 2
    j = np.eye(n) - np.ones((n, n)) / n
    b = -0.5 * j @ d2 @ j
    evals, evecs = np.linalg.eigh(b)
    idx = np.argsort(evals)[::-1][: max(2, min(6, n - 1))]
    embed = evecs[:, idx] * np.sqrt(np.clip(evals[idx], 0, None))
    # Simple k-means
    rng = np.random.default_rng(42)
    centers = embed[rng.choice(n, size=k, replace=False)]
    labels = np.zeros(n, dtype=int)
    for _ in range(30):
        dist = ((embed[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        labels = dist.argmin(axis=1)
        for c in range(k):
            mask = labels == c
            if mask.any():
                centers[c] = embed[mask].mean(axis=0)
    return [int(x) + 1 for x in labels]


@tool
def calculate_hbond_lifetimes(
    topology_file: str,
    trajectory_file: str,
    selection1: str = "protein",
    selection2: str = "protein",
    occupancy_csv: str = "",
    output_file: str = "hbond_lifetimes.csv",
    working_dir: Optional[str] = None,
    d_a_cutoff: float = 3.5,
    angle_cutoff: float = 150.0,
    frame_interval: int = 1,
    min_occupancy: float = 0.05,
) -> Dict[str, Any]:
    """
    Hydrogen-bond continuous lifetimes from the occupancy time series.

    If ``occupancy_csv`` from ``calculate_hbond_occupancy`` is present, pair
    names are reused. Otherwise H-bonds are detected on the trajectory.
    """
    if not HAS_DEPS:
        return {"success": False, "error": "MDAnalysis and numpy are required"}
    top, traj = Path(topology_file), Path(trajectory_file)
    if not top.is_file() or not traj.is_file():
        return {"success": False, "error": f"Missing files: {top}, {traj}"}
    try:
        u = mda.Universe(str(top), str(traj))
        step = max(1, int(frame_interval or 1))
        hb = hydrogenbonds.HydrogenBondAnalysis(
            u,
            donors_sel=f"(({selection1}) or ({selection2})) and (name N or name O or name ND1 or name ND2 or name NE or name NE1 or name NE2 or name NH1 or name NH2 or name NZ or name OG or name OG1 or name OH)",
            acceptors_sel=f"(({selection1}) or ({selection2})) and (name N or name O or name OD1 or name OD2 or name OE1 or name OE2 or name OG or name OG1 or name OH or name ND1 or name NE2)",
            between=[selection1, selection2],
            d_a_cutoff=float(d_a_cutoff),
            d_h_a_angle_cutoff=float(angle_cutoff),
        )
        hb.run(step=step)
        n_frames = len(u.trajectory[::step])
        dt_ps = float(u.trajectory.dt) * step if n_frames else 0.0
        frame_to_i = {int(ts.frame): i for i, ts in enumerate(u.trajectory[::step])}
        pair_frames: Dict[str, set] = defaultdict(set)
        rows_hb = hb.results.hbonds
        if rows_hb is not None and len(rows_hb):
            for row in rows_hb:
                frame = int(row[0])
                idx = frame_to_i.get(frame)
                if idx is None:
                    continue
                donor = u.atoms[int(row[1])].residue
                acceptor = u.atoms[int(row[3])].residue
                key = f"{donor.resname}{donor.resid}-{acceptor.resname}{acceptor.resid}"
                pair_frames[key].add(idx)

        out_rows: List[List[Any]] = []
        for pair, frames in pair_frames.items():
            occ = len(frames) / max(n_frames, 1)
            if occ < float(min_occupancy):
                continue
            present = np.zeros(n_frames, dtype=bool)
            for i in frames:
                present[i] = True
            mean_life, n_events = _mean_run_length(present, dt_ps)
            out_rows.append([pair, f"{100.0 * occ:.2f}", f"{mean_life:.3f}", n_events])
        out_rows.sort(key=lambda r: -float(r[1]))
        out = _out_dir(working_dir, output_file)
        with out.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["pair", "occupancy_pct", "mean_lifetime_ps", "n_events"])
            w.writerows(out_rows)
        mean_life = (
            float(np.mean([float(r[2]) for r in out_rows])) if out_rows else 0.0
        )
        summary = {
            "success": True,
            "n_pairs": len(out_rows),
            "mean_lifetime_ps": mean_life,
            "output_file": str(out),
            "occupancy_csv": occupancy_csv or "",
        }
        if working_dir:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Hbond_lifetimes",
                statistics={"n_pairs": len(out_rows), "mean_lifetime_ps": mean_life},
                files={"csv": str(out)},
            )
        return summary
    except Exception as exc:
        logger.exception("calculate_hbond_lifetimes failed")
        return {"success": False, "error": str(exc)}


def _mean_run_length(present: np.ndarray, dt_ps: float) -> tuple:
    runs: List[int] = []
    run = 0
    for flag in present:
        if flag:
            run += 1
        elif run:
            runs.append(run)
            run = 0
    if run:
        runs.append(run)
    if not runs:
        return 0.0, 0
    return float(np.mean(runs) * max(dt_ps, 0.0)), len(runs)
