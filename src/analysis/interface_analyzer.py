"""
Protein–protein interface interactions.

Tools:
  - ``calculate_hbond_occupancy`` — H-bond occupancy between two selections
  - ``calculate_salt_bridge_distances`` — charged-pair distances and occupancy
"""
from __future__ import annotations

import csv
import json
import logging
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import distances as mda_distances
    from MDAnalysis.analysis.hydrogenbonds import HydrogenBondAnalysis

    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    logger.warning("MDAnalysis not available — interface analysis disabled")

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

try:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    HAS_MPL = True
except ImportError:
    HAS_MPL = False

HBOND_DA_CUTOFF = 3.5
HBOND_ANGLE = 150.0
SALT_CUTOFF = 4.0
SALT_TRACK_CUTOFF = 6.0

DONOR_NAMES = "name N NZ NE NH1 NH2 ND1 ND2 OG OG1 OH SG NE1 NE2"
ACCEPTOR_NAMES = "name O OG OG1 OG2 OD1 OD2 OE1 OE2 OH ND1 ND2 NE NE2 NH1 NH2 NZ N"

CATION_ATOMS = {
    "ARG": ("CZ", "NH1", "NH2"),
    "LYS": ("NZ",),
    "HIS": ("ND1", "NE2"),
    "HIE": ("ND1", "NE2"),
    "HID": ("ND1", "NE2"),
    "HIP": ("ND1", "NE2"),
}
ANION_ATOMS = {
    "ASP": ("OD1", "OD2"),
    "ASH": ("OD1", "OD2"),
    "GLU": ("OE1", "OE2"),
    "GLH": ("OE1", "OE2"),
}


def _output_stem(output_file: Optional[str], default: str) -> str:
    name = Path(output_file or default).name
    return Path(name).stem


def _load_resindex_labels(working_dir: Optional[str], topology_file: str) -> Dict[int, Tuple[str, int, str]]:
    labels: Dict[int, Tuple[str, int, str]] = {}
    try:
        from .chain_residue_map import find_chain_residue_map, load_chain_residue_map

        found = find_chain_residue_map(working_dir, topology_file)
        if not found:
            return labels
        data = load_chain_residue_map(found) or {}
        for chain_id, rec in (data.get("chains") or {}).items():
            for resindex, pdb_resid, resname in zip(
                rec.get("traj_resindices") or [],
                rec.get("pdb_resids") or [],
                rec.get("pdb_resnames") or [],
            ):
                labels[int(resindex)] = (str(chain_id), int(pdb_resid), str(resname))
    except Exception as exc:
        logger.warning("Could not load chain residue map for interface labels: %s", exc)
    return labels


def residue_tag(labels: Dict[int, Tuple[str, int, str]], residue) -> str:
    mapped = labels.get(int(residue.resindex))
    if mapped:
        chain, pdb_resid, resname = mapped
        return f"{chain}:{resname.capitalize()}{pdb_resid}"
    chain = getattr(residue, "segid", "") or getattr(residue, "chainID", "") or "?"
    return f"{chain}:{residue.resname.capitalize()}{int(residue.resid)}"


def atom_tag(labels: Dict[int, Tuple[str, int, str]], atom) -> str:
    return f"{residue_tag(labels, atom.residue)}-{atom.name}"


def _write_csv(path: Path, header: Sequence[str], rows: Sequence[Sequence[Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(list(header))
        writer.writerows(rows)


def _style_axes(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", linestyle=":", alpha=0.4)


def _barh_occupancy(path: Path, labels_y: List[str], values: List[float], title: str, xlabel: str, color: str) -> None:
    if not HAS_MPL or not labels_y:
        return
    fig, ax = plt.subplots(figsize=(8.8, max(3.5, 0.32 * len(labels_y) + 1.2)), dpi=150)
    ax.barh(labels_y[::-1], values[::-1], color=color)
    ax.set_xlabel(xlabel)
    ax.set_title(title)
    ax.set_xlim(0, 100)
    _style_axes(ax)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def compute_hbond_occupancy_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    selection1: str,
    selection2: str,
    label1: str = "group1",
    label2: str = "group2",
    d_a_cutoff: float = HBOND_DA_CUTOFF,
    angle_cutoff: float = HBOND_ANGLE,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    if not HAS_MDA or not HAS_NUMPY:
        return {"success": False, "error": "MDAnalysis and numpy are required for H-bond occupancy"}

    ag1 = u.select_atoms(selection1)
    ag2 = u.select_atoms(selection2)
    if len(ag1) == 0:
        return {"success": False, "error": f"Selection 1 matched 0 atoms: '{selection1}'"}
    if len(ag2) == 0:
        return {"success": False, "error": f"Selection 2 matched 0 atoms: '{selection2}'"}

    labels = _load_resindex_labels(working_dir, topology_file)
    union = f"({selection1}) or ({selection2})"
    step = max(1, int(frame_interval or 1))
    hb = HydrogenBondAnalysis(
        u,
        donors_sel=f"({union}) and ({DONOR_NAMES})",
        acceptors_sel=f"({union}) and ({ACCEPTOR_NAMES})",
        between=[selection1, selection2],
        d_a_cutoff=float(d_a_cutoff),
        d_h_a_angle_cutoff=float(angle_cutoff),
    )
    hb.run(step=step)

    n_frames = len(u.trajectory[::step])
    times_ns = np.array([ts.time / 1000.0 for ts in u.trajectory[::step]], dtype=float)
    frame_to_i = {int(ts.frame): i for i, ts in enumerate(u.trajectory[::step])}
    counts = np.zeros(n_frames, dtype=int)

    atom_frames: Dict[Tuple[str, str], set] = defaultdict(set)
    res_frames: Dict[Tuple[str, str], set] = defaultdict(set)
    atom_examples: Dict[Tuple[str, str], Tuple[float, float]] = {}

    rows = hb.results.hbonds
    if rows is not None and len(rows):
        for row in rows:
            frame = int(row[0])
            idx = frame_to_i.get(frame)
            if idx is None:
                continue
            donor = u.atoms[int(row[1])]
            acceptor = u.atoms[int(row[3])]
            dist = float(row[4])
            angle = float(row[5])
            counts[idx] += 1
            d_tag = atom_tag(labels, donor)
            a_tag = atom_tag(labels, acceptor)
            d_res = residue_tag(labels, donor.residue)
            a_res = residue_tag(labels, acceptor.residue)
            atom_key = (d_tag, a_tag)
            res_key = (d_res, a_res)
            atom_frames[atom_key].add(frame)
            res_frames[res_key].add(frame)
            prev = atom_examples.get(atom_key)
            if prev is None or dist < prev[0]:
                atom_examples[atom_key] = (dist, angle)

    atom_rows = []
    for (donor, acceptor), frames in atom_frames.items():
        occ = 100.0 * len(frames) / max(n_frames, 1)
        dist, angle = atom_examples[(donor, acceptor)]
        atom_rows.append([donor, acceptor, len(frames), n_frames, f"{occ:.2f}", f"{dist:.3f}", f"{angle:.1f}"])
    atom_rows.sort(key=lambda r: -float(r[4]))

    res_rows = []
    for (donor, acceptor), frames in res_frames.items():
        occ = 100.0 * len(frames) / max(n_frames, 1)
        res_rows.append([donor, acceptor, len(frames), n_frames, f"{occ:.2f}"])
    res_rows.sort(key=lambda r: -float(r[4]))

    stem = _output_stem(output_file, f"hbond_occupancy_{label1}_vs_{label2}.csv")
    occ_csv = f"{stem}.csv"
    atom_csv = f"{stem}_atoms.csv"
    count_csv = f"{stem}_count.csv"
    occ_png = f"{stem}.png"
    count_png = f"{stem}_count.png"

    _write_csv(
        Path(occ_csv),
        ["donor_residue", "acceptor_residue", "n_frames", "n_total_frames", "occupancy_pct"],
        res_rows,
    )
    _write_csv(
        Path(atom_csv),
        ["donor", "acceptor", "n_frames", "n_total_frames", "occupancy_pct", "min_DA_A", "angle_at_min"],
        atom_rows,
    )
    _write_csv(
        Path(count_csv),
        ["frame", "time_ns", "n_hbonds"],
        [[i, f"{t:.4f}", int(c)] for i, (t, c) in enumerate(zip(times_ns, counts))],
    )

    top = res_rows[:20]
    _barh_occupancy(
        Path(occ_png),
        [f"{a} → {b}" for a, b, *_ in top],
        [float(r[4]) for r in top],
        f"H-bond occupancy ({label1} ↔ {label2})",
        "Occupancy (%)",
        "#2c5f8a",
    )
    if HAS_MPL:
        fig, ax = plt.subplots(figsize=(8.5, 4.2), dpi=150)
        ax.plot(times_ns, counts, color="#1f4e79", lw=1.1)
        if n_frames:
            ax.axhline(float(np.mean(counts)), color="#c0392b", ls="--", lw=1, label=f"mean = {np.mean(counts):.1f}")
        ax.set_xlabel("Time (ns)")
        ax.set_ylabel("H-bonds")
        ax.set_title(f"Interface H-bonds  (D–A ≤ {d_a_cutoff} Å, ∠ ≥ {angle_cutoff:.0f}°)")
        _style_axes(ax)
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(count_png)
        plt.close(fig)

    stats = {
        "mean_hbonds": float(np.mean(counts)) if n_frames else 0.0,
        "std_hbonds": float(np.std(counts)) if n_frames else 0.0,
        "min_hbonds": int(np.min(counts)) if n_frames else 0,
        "max_hbonds": int(np.max(counts)) if n_frames else 0,
        "n_unique_residue_pairs": len(res_rows),
        "n_unique_atom_pairs": len(atom_rows),
        "n_frames": n_frames,
    }
    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type=f"HBond_Occupancy_{label1}_vs_{label2}",
                statistics=stats,
                files={
                    "topology": topology_file,
                    "trajectory": trajectory_file,
                    "data": occ_csv,
                    "atoms": atom_csv,
                    "count": count_csv,
                    "plot": occ_png,
                },
                metadata={
                    "selection1": selection1,
                    "selection2": selection2,
                    "label1": label1,
                    "label2": label2,
                    "d_a_cutoff_A": d_a_cutoff,
                    "angle_cutoff_deg": angle_cutoff,
                    "top_residue_pairs": [
                        {"donor": r[0], "acceptor": r[1], "occupancy_pct": float(r[4])}
                        for r in res_rows[:15]
                    ],
                },
            )
        except Exception as exc:
            logger.warning("Failed to write H-bond occupancy summary: %s", exc)

    return {
        "success": True,
        "output_file": occ_csv,
        "count_file": count_csv,
        "plot_file": occ_png,
        "selection1": selection1,
        "selection2": selection2,
        "label1": label1,
        "label2": label2,
        **stats,
        "top_residue_pairs": [
            {"donor": r[0], "acceptor": r[1], "occupancy_pct": float(r[4])} for r in res_rows[:15]
        ],
        "message": (
            f"H-bond occupancy ({label1} vs {label2}): mean {stats['mean_hbonds']:.1f}/frame, "
            f"{stats['n_unique_residue_pairs']} residue pairs"
        ),
    }


def _charged_groups(u, selection: str, labels: Dict[int, Tuple[str, int, str]], include_nterm: bool):
    ag = u.select_atoms(selection)
    groups = []
    seen = set()
    resindices = [int(r.resindex) for r in ag.residues]
    nterm_index = min(resindices) if resindices else None
    for res in ag.residues:
        key = int(res.resindex)
        if key in seen:
            continue
        seen.add(key)
        name = res.resname
        tag = residue_tag(labels, res)
        if name in CATION_ATOMS:
            atoms = res.atoms.select_atoms("name " + " ".join(CATION_ATOMS[name]))
            if len(atoms):
                groups.append((tag, "cation", atoms))
        if name in ANION_ATOMS:
            atoms = res.atoms.select_atoms("name " + " ".join(ANION_ATOMS[name]))
            if len(atoms):
                groups.append((tag, "anion", atoms))
        if include_nterm and nterm_index is not None and key == nterm_index:
            n_atom = res.atoms.select_atoms("name N")
            if len(n_atom):
                groups.append((f"{tag}-Nter", "cation", n_atom))
    return groups


def compute_salt_bridge_distances_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    selection1: str,
    selection2: str,
    label1: str = "group1",
    label2: str = "group2",
    cutoff: float = SALT_CUTOFF,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    if not HAS_MDA or not HAS_NUMPY:
        return {"success": False, "error": "MDAnalysis and numpy are required for salt-bridge distances"}

    labels = _load_resindex_labels(working_dir, topology_file)
    group1 = _charged_groups(u, selection1, labels, include_nterm=True)
    group2 = _charged_groups(u, selection2, labels, include_nterm=False)
    pairs = []
    for tag1, kind1, atoms1 in group1:
        for tag2, kind2, atoms2 in group2:
            if {kind1, kind2} == {"cation", "anion"}:
                pairs.append((f"{tag1} – {tag2}", atoms1, atoms2, tag1, tag2))

    if not pairs:
        return {"success": False, "error": "No complementary charged residue pairs between the selections"}

    step = max(1, int(frame_interval or 1))
    frames = list(u.trajectory[::step])
    n_frames = len(frames)
    times_ns = np.array([ts.time / 1000.0 for ts in frames], dtype=float)
    distances = np.full((n_frames, len(pairs)), np.nan, dtype=float)

    for i, ts in enumerate(frames):
        box = getattr(ts, "dimensions", None)
        for j, (_, ag1, ag2, _, _) in enumerate(pairs):
            dist = mda_distances.distance_array(ag1.positions, ag2.positions, box=box)
            distances[i, j] = float(np.min(dist))

    occ_rows = []
    keep_idx = []
    for j, (pair_label, _, _, tag1, tag2) in enumerate(pairs):
        d = distances[:, j]
        occ4 = 100.0 * float(np.mean(d < float(cutoff)))
        occ35 = 100.0 * float(np.mean(d < 3.5))
        if float(np.min(d)) <= SALT_TRACK_CUTOFF or occ4 > 0:
            keep_idx.append(j)
        occ_rows.append(
            [
                tag1,
                tag2,
                pair_label,
                f"{float(np.mean(d)):.3f}",
                f"{float(np.std(d)):.3f}",
                f"{float(np.min(d)):.3f}",
                f"{float(np.max(d)):.3f}",
                f"{occ4:.2f}",
                f"{occ35:.2f}",
            ]
        )
    occ_rows.sort(key=lambda r: (-float(r[7]), float(r[5])))

    stem = _output_stem(output_file, f"saltbridge_occupancy_{label1}_vs_{label2}.csv")
    occ_csv = f"{stem}.csv"
    dist_csv = f"{stem}_distances.csv"
    occ_png = f"{stem}.png"
    dist_png = f"{stem}_distances.png"

    _write_csv(
        Path(occ_csv),
        [
            "group1",
            "group2",
            "pair",
            "mean_A",
            "std_A",
            "min_A",
            "max_A",
            "occupancy_4A_pct",
            "occupancy_3.5A_pct",
        ],
        occ_rows,
    )
    header = ["frame", "time_ns"] + [pairs[j][0] for j in keep_idx]
    ts_rows = []
    for i, t in enumerate(times_ns):
        ts_rows.append([i, f"{t:.4f}"] + [f"{distances[i, j]:.3f}" for j in keep_idx])
    _write_csv(Path(dist_csv), header, ts_rows)

    persistent = [r for r in occ_rows if float(r[7]) >= 5.0][:15]
    _barh_occupancy(
        Path(occ_png),
        [r[2] for r in persistent] or [r[2] for r in occ_rows[:8]],
        [float(r[7]) for r in persistent] or [float(r[7]) for r in occ_rows[:8]],
        f"Salt-bridge occupancy ({label1} ↔ {label2})",
        f"Occupancy (% of frames < {float(cutoff):.1f} Å)",
        "#8b3a3a",
    )

    plot_pairs = [r for r in occ_rows if float(r[7]) >= 10.0][:8] or occ_rows[:6]
    if HAS_MPL and plot_pairs:
        fig, ax = plt.subplots(figsize=(9.2, 4.6), dpi=150)
        colors = plt.cm.tab10(np.linspace(0, 0.9, max(len(plot_pairs), 1)))
        name_to_idx = {pairs[j][0]: j for j in range(len(pairs))}
        for color, row in zip(colors, plot_pairs):
            j = name_to_idx[row[2]]
            ax.plot(times_ns, distances[:, j], lw=1.05, color=color, label=row[2])
        ax.axhline(float(cutoff), color="0.35", ls="--", lw=1, label=f"{float(cutoff):.1f} Å cutoff")
        ax.set_xlabel("Time (ns)")
        ax.set_ylabel("Min charged-atom distance (Å)")
        ax.set_title(f"Salt-bridge distances ({label1} ↔ {label2})")
        ax.set_ylim(1.5, 12)
        _style_axes(ax)
        ax.legend(frameon=False, fontsize=7, loc="upper right")
        fig.tight_layout()
        fig.savefig(dist_png)
        plt.close(fig)

    top_pairs = [
        {
            "pair": r[2],
            "mean_A": float(r[3]),
            "min_A": float(r[5]),
            "occupancy_4A_pct": float(r[7]),
        }
        for r in occ_rows[:15]
    ]
    stats = {
        "n_candidate_pairs": len(pairs),
        "n_tracked_pairs": len(keep_idx),
        "n_frames": n_frames,
        "cutoff_A": float(cutoff),
    }
    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type=f"SaltBridge_{label1}_vs_{label2}",
                statistics=stats,
                files={
                    "topology": topology_file,
                    "trajectory": trajectory_file,
                    "data": occ_csv,
                    "distances": dist_csv,
                    "plot": occ_png,
                },
                metadata={
                    "selection1": selection1,
                    "selection2": selection2,
                    "label1": label1,
                    "label2": label2,
                    "top_pairs": top_pairs,
                },
            )
        except Exception as exc:
            logger.warning("Failed to write salt-bridge summary: %s", exc)

    return {
        "success": True,
        "output_file": occ_csv,
        "distance_file": dist_csv,
        "plot_file": occ_png,
        "selection1": selection1,
        "selection2": selection2,
        "label1": label1,
        "label2": label2,
        "top_pairs": top_pairs,
        **stats,
        "message": (
            f"Salt bridges ({label1} vs {label2}): {len(pairs)} complementary pairs, "
            f"{len(keep_idx)} approached ≤ {SALT_TRACK_CUTOFF:.0f} Å"
        ),
    }


def _run_with_universe(compute_fn, topology_file, trajectory_file, working_dir, **kwargs):
    original_dir = None
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)
        if not HAS_MDA:
            return {"success": False, "error": "MDAnalysis is required"}
        if not os.path.exists(topology_file):
            return {"success": False, "error": f"Topology file not found: {topology_file}"}
        if not os.path.exists(trajectory_file):
            return {"success": False, "error": f"Trajectory file not found: {trajectory_file}"}
        u = mda.Universe(topology_file, trajectory_file)
        return compute_fn(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            working_dir=working_dir,
            **kwargs,
        )
    except Exception as exc:
        logger.exception("%s failed", compute_fn.__name__)
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)


@tool
def calculate_hbond_occupancy(
    topology_file: str,
    trajectory_file: str,
    selection1: str,
    selection2: str,
    label1: str = "group1",
    label2: str = "group2",
    d_a_cutoff: float = HBOND_DA_CUTOFF,
    angle_cutoff: float = HBOND_ANGLE,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    """
    Hydrogen-bond occupancy between two protein groups over the trajectory.

    Use for protein–protein interfaces (chain–chain or residue-range vs chain).
    Reports residue-pair occupancy (% of frames with a D–A H-bond) and a
    per-frame H-bond count. Not a protein–ligand contact counter.

    Args:
        topology_file: Topology file (.tpr, .gro, .pdb)
        trajectory_file: Trajectory file (.xtc, .trr)
        selection1: First MDAnalysis selection (e.g. "chainID B and resid 1:34")
        selection2: Second MDAnalysis selection (e.g. "chainID A")
        label1: Short label for selection 1 (used in qualified filenames)
        label2: Short label for selection 2
        d_a_cutoff: Donor–acceptor distance cutoff in Å (default 3.5)
        angle_cutoff: D–H–A angle cutoff in degrees (default 150)
        output_file: Occupancy CSV basename, e.g. hbond_occupancy_B1to34_vs_A.csv
        working_dir: Analysis output directory
        frame_interval: Process every Nth frame (default 1)

    Returns:
        Dict with occupancy statistics, top residue pairs, and output paths.

    Standard outputs: hbond_occupancy.csv + .png; subset: hbond_occupancy_{qualifier}.csv
    """
    return _run_with_universe(
        compute_hbond_occupancy_from_universe,
        topology_file,
        trajectory_file,
        working_dir,
        selection1=selection1,
        selection2=selection2,
        label1=label1,
        label2=label2,
        d_a_cutoff=d_a_cutoff,
        angle_cutoff=angle_cutoff,
        output_file=output_file,
        frame_interval=frame_interval,
    )


@tool
def calculate_salt_bridge_distances(
    topology_file: str,
    trajectory_file: str,
    selection1: str,
    selection2: str,
    label1: str = "group1",
    label2: str = "group2",
    cutoff: float = SALT_CUTOFF,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    """
    Salt-bridge distances and occupancy between two protein groups.

    Complementary charged pairs (Arg/Lys/His/N-terminus vs Asp/Glu) are tracked
    as the minimum charged-atom distance each frame. Occupancy is the fraction
    of frames below ``cutoff`` Å (default 4.0). Use for protein–protein interfaces.

    Args:
        topology_file: Topology file (.tpr, .gro, .pdb)
        trajectory_file: Trajectory file (.xtc, .trr)
        selection1: First MDAnalysis selection
        selection2: Second MDAnalysis selection
        label1: Short label for selection 1
        label2: Short label for selection 2
        cutoff: Occupancy distance cutoff in Å (default 4.0)
        output_file: Occupancy CSV basename, e.g. saltbridge_occupancy_B1to34_vs_A.csv
        working_dir: Analysis output directory
        frame_interval: Process every Nth frame (default 1)

    Returns:
        Dict with pair occupancies, top salt bridges, and output paths.

    Standard outputs: saltbridge_occupancy.csv + .png; subset: saltbridge_occupancy_{qualifier}.csv
    """
    return _run_with_universe(
        compute_salt_bridge_distances_from_universe,
        topology_file,
        trajectory_file,
        working_dir,
        selection1=selection1,
        selection2=selection2,
        label1=label1,
        label2=label2,
        cutoff=cutoff,
        output_file=output_file,
        frame_interval=frame_interval,
    )
