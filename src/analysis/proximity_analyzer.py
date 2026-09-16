"""
Proximity / interface analysis for arbitrary atom groups.

Tools:
  - ``identify_nearby_residues`` — freeze residues of one group within a cutoff
    of another group at a chosen frame (usually frame 0)
  - ``calculate_min_heavy_atom_distance`` — per-frame minimum heavy-atom distance
    between two selections

Neighbor identity is taken once and then held fixed. Downstream RMSF / COM /
min-distance steps consume the JSON via ``selection_from_file``.
"""
from __future__ import annotations

import csv
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis import distances as mda_distances

    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    logger.warning("MDAnalysis not available — proximity analysis disabled")

try:
    import numpy as np

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


SELECTION_FROM_FILE_KEYS = {
    "selection_from_file": "selection",
    "selection1_from_file": "selection1",
    "selection2_from_file": "selection2",
    "query_selection_from_file": "query_selection",
    "neighbor_selection_from_file": "neighbor_selection",
}

_SELECTION_KEY_DEFAULTS = {
    "selection": "mda_selection_ca",
    "selection1": "mda_selection_heavy",
    "selection2": "mda_selection_heavy",
    "query_selection": "mda_selection",
    "neighbor_selection": "mda_selection_heavy",
}


def _resolve_nearby_path(path: str, working_dir: Optional[str] = None) -> Optional[Path]:
    raw = Path(str(path))
    candidates = [raw]
    if working_dir:
        candidates.append(Path(working_dir) / raw.name)
        candidates.append(Path(working_dir) / raw)
    if not raw.is_absolute():
        candidates.append(Path.cwd() / raw)
        candidates.append(Path.cwd() / raw.name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def load_mda_selection(
    path: str,
    working_dir: Optional[str] = None,
    selection_key: Optional[str] = None,
) -> Optional[str]:
    """Read ``mda_selection*`` from an identify_nearby_residues JSON (or CSV fallback)."""
    found = _resolve_nearby_path(path, working_dir)
    if found is None:
        logger.warning("selection_from_file not found: %s", path)
        return None

    if found.suffix.lower() == ".json":
        with found.open(encoding="utf-8") as handle:
            data = json.load(handle)
        keys: List[str] = []
        if selection_key:
            keys.append(selection_key)
        keys.extend(
            [
                "mda_selection_heavy",
                "mda_selection_ca",
                "mda_selection",
                "pdb_selection",
            ]
        )
        for key in keys:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    if found.suffix.lower() == ".csv":
        indices: List[int] = []
        with found.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                raw = row.get("resindex") or row.get("traj_resindex")
                if raw in (None, ""):
                    continue
                try:
                    indices.append(int(raw))
                except ValueError:
                    continue
        if not indices:
            return None
        unique = sorted(set(indices))
        return "resindex " + " ".join(str(i) for i in unique)

    return None


def apply_selection_from_files(
    params: Dict[str, Any],
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """Copy *params* and fill selection strings from nearby-residue JSON/CSV files."""
    out = dict(params)
    explicit_key = out.get("selection_key")
    for src_key, dest_key in SELECTION_FROM_FILE_KEYS.items():
        path = out.get(src_key)
        if not path:
            continue
        key = explicit_key or _SELECTION_KEY_DEFAULTS.get(dest_key)
        selection = load_mda_selection(str(path), working_dir, selection_key=key)
        if selection:
            out[dest_key] = selection
            logger.info(
                "Loaded %s from %s (%s) → %s",
                dest_key, path, key, selection[:120],
            )
        else:
            logger.warning(
                "Could not load %s from %s; keeping %s=%r",
                dest_key, path, dest_key, out.get(dest_key),
            )
    return out


def format_resindex_list(indices: Sequence[int]) -> str:
    unique = sorted({int(i) for i in indices})
    if not unique:
        return ""
    return "resindex " + " ".join(str(i) for i in unique)


def freeze_nearby_residues(
    universe,
    *,
    query_selection: str,
    neighbor_selection: str,
    cutoff: float = 15.0,
    frame: int = 0,
) -> Tuple[Any, List[Dict[str, Any]], Dict[str, Any]]:
    """
    Select neighbor residues within *cutoff* Å of *query_selection* at *frame*.

    Returns (neighbor AtomGroup of all atoms in those residues, residue rows, meta).
    """
    n_frames = len(universe.trajectory)
    if frame < 0 or frame >= n_frames:
        raise ValueError(f"frame {frame} is outside trajectory (n_frames={n_frames})")

    universe.trajectory[frame]
    query = universe.select_atoms(query_selection)
    if len(query) == 0:
        raise ValueError(f"Query selection matched 0 atoms: '{query_selection}'")

    search = universe.select_atoms(neighbor_selection)
    if len(search) == 0:
        raise ValueError(f"Neighbor selection matched 0 atoms: '{neighbor_selection}'")

    nearby = universe.select_atoms(
        f"({neighbor_selection}) and around {float(cutoff)} ({query_selection})"
    )
    residue_indices = sorted({int(atom.resindex) for atom in nearby})
    if not residue_indices:
        raise ValueError(
            f"No atoms in '{neighbor_selection}' within {cutoff} Å of "
            f"'{query_selection}' at frame {frame}."
        )

    frozen = universe.residues[residue_indices].atoms
    rows: List[Dict[str, Any]] = []
    query_heavy = query.select_atoms("not name H*")
    for residue in universe.residues[residue_indices]:
        res_heavy = residue.atoms.select_atoms("not name H*")
        min_dist = None
        if HAS_NUMPY and len(query_heavy) and len(res_heavy):
            dist = mda_distances.distance_array(
                res_heavy.positions,
                query_heavy.positions,
                box=getattr(universe.trajectory.ts, "dimensions", None),
            )
            if dist.size:
                min_dist = float(np.min(dist))
        chain = ""
        if hasattr(residue, "segid") and residue.segid:
            chain = str(residue.segid).strip()
        rows.append({
            "chain": chain,
            "resid": int(residue.resid),
            "resname": str(residue.resname),
            "resindex": int(residue.resindex),
            "n_atoms": int(len(residue.atoms)),
            "min_distance_A": min_dist,
        })

    resindex_sel = format_resindex_list(residue_indices)
    meta = {
        "query_selection": query_selection,
        "neighbor_selection": neighbor_selection,
        "cutoff_A": float(cutoff),
        "frame": int(frame),
        "query_atom_count": int(len(query)),
        "neighbor_atom_count": int(len(frozen)),
        "n_residues": len(rows),
        "mda_selection": resindex_sel,
        "mda_selection_ca": f"name CA and {resindex_sel}" if resindex_sel else "",
        "mda_selection_heavy": f"(not name H*) and {resindex_sel}" if resindex_sel else "",
        "residues": rows,
    }
    return frozen, rows, meta


def _write_nearby_outputs(
    meta: Dict[str, Any],
    output_file: str,
) -> Dict[str, str]:
    json_path = Path(output_file)
    if json_path.suffix.lower() not in {".json", ".csv"}:
        json_path = json_path.with_suffix(".json")
    csv_path = json_path.with_suffix(".csv")
    if json_path.suffix.lower() == ".csv":
        csv_path = json_path
        json_path = json_path.with_suffix(".json")

    payload = {k: v for k, v in meta.items()}
    json_path.parent.mkdir(parents=True, exist_ok=True)
    with json_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
        handle.write("\n")

    rows = meta.get("residues") or []
    fieldnames = ["chain", "resid", "resname", "resindex", "n_atoms", "min_distance_A"]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})

    return {"json": str(json_path), "csv": str(csv_path)}


def compute_nearby_residues_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    query_selection: str,
    neighbor_selection: str,
    cutoff: float = 15.0,
    frame: int = 0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    if not HAS_MDA:
        return {"success": False, "error": "MDAnalysis is required for identify_nearby_residues"}
    try:
        _frozen, rows, meta = freeze_nearby_residues(
            u,
            query_selection=query_selection,
            neighbor_selection=neighbor_selection,
            cutoff=cutoff,
            frame=frame,
        )
    except Exception as exc:
        return {"success": False, "error": str(exc)}

    output_filename = output_file or "nearby_residues.json"
    files = _write_nearby_outputs(meta, output_filename)

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Nearby_Residues",
                statistics={
                    "n_residues": meta["n_residues"],
                    "cutoff_A": meta["cutoff_A"],
                    "frame": meta["frame"],
                    "query_atom_count": meta["query_atom_count"],
                    "neighbor_atom_count": meta["neighbor_atom_count"],
                },
                files={
                    "topology": topology_file,
                    "trajectory": trajectory_file,
                    "data": files["json"],
                    "table": files["csv"],
                },
                metadata={
                    "query_selection": query_selection,
                    "neighbor_selection": neighbor_selection,
                    "mda_selection": meta["mda_selection"],
                    "residues": rows,
                },
            )
        except Exception as exc:
            logger.warning("Failed to write nearby-residue summary: %s", exc)

    return {
        "success": True,
        "n_residues": meta["n_residues"],
        "cutoff_A": meta["cutoff_A"],
        "frame": meta["frame"],
        "query_selection": query_selection,
        "neighbor_selection": neighbor_selection,
        "mda_selection": meta["mda_selection"],
        "mda_selection_ca": meta["mda_selection_ca"],
        "mda_selection_heavy": meta["mda_selection_heavy"],
        "residues": rows,
        "output_file": files["json"],
        "csv_file": files["csv"],
        "output_files": files,
        "message": (
            f"Found {meta['n_residues']} neighbor residues within {meta['cutoff_A']:.1f} Å "
            f"of query at frame {meta['frame']}"
        ),
    }


@tool
def identify_nearby_residues(
    topology_file: str,
    trajectory_file: str,
    query_selection: str,
    neighbor_selection: str,
    cutoff: float = 15.0,
    frame: int = 0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Identify residues of one group within a cutoff of another group at one frame.

    Use this when the user asks to find residues "within X Å" of a chain, domain,
    ligand, or residue range (typically at frame 0), then analyse those same
    residues over the trajectory. The neighbor set is frozen; write qualified
    filenames such as nearby_residues_A_near_B1to34.json.

    Args:
        topology_file: Topology file (.tpr, .gro, .pdb)
        trajectory_file: Trajectory file (.xtc, .trr)
        query_selection: Reference group (e.g. "chainID B and resid 1:34")
        neighbor_selection: Group to search (e.g. "chainID A")
        cutoff: Distance cutoff in Ångström (default 15.0)
        frame: Trajectory frame used to define neighbors (default 0)
        output_file: JSON basename (also writes a matching .csv table)
        working_dir: Analysis output directory

    Returns:
        Dict with residue list, MDAnalysis selection strings, and output paths.
    """
    original_dir = None
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)
        if not HAS_MDA:
            return {"success": False, "error": "MDAnalysis is required for identify_nearby_residues"}
        if not os.path.exists(topology_file):
            return {"success": False, "error": f"Topology file not found: {topology_file}"}
        if not os.path.exists(trajectory_file):
            return {"success": False, "error": f"Trajectory file not found: {trajectory_file}"}

        u = mda.Universe(topology_file, trajectory_file)
        return compute_nearby_residues_from_universe(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            query_selection=query_selection,
            neighbor_selection=neighbor_selection,
            cutoff=cutoff,
            frame=frame,
            output_file=output_file,
            working_dir=working_dir,
        )
    except Exception as exc:
        logger.exception("identify_nearby_residues failed")
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)


def finalize_min_distance_result(
    frames: list,
    times: list,
    distances: list,
    *,
    selection1: str,
    selection2: str,
    label1: str,
    label2: str,
    output_file: Optional[str],
    topology_file: str,
    trajectory_file: str,
    working_dir: Optional[str],
    frame_interval: int = 1,
) -> Dict[str, Any]:
    if not distances:
        return {"success": False, "error": "No min-distance values collected"}

    distances_arr = np.array(distances, dtype=float)
    mean_dist = float(np.mean(distances_arr))
    std_dist = float(np.std(distances_arr))
    min_dist = float(np.min(distances_arr))
    max_dist = float(np.max(distances_arr))

    if not output_file:
        output_file = "min_distance.csv"

    with open(output_file, "w") as handle:
        handle.write("frame,time_ns,min_distance_angstrom\n")
        for fr, t, d in zip(frames, times, distances):
            handle.write(f"{fr},{t / 1000.0:.4f},{d:.4f}\n")

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type=f"Min_Heavy_Atom_Distance_{label1}_vs_{label2}",
                statistics={
                    "n_frames": len(distances),
                    "mean_distance_angstrom": mean_dist,
                    "std_distance_angstrom": std_dist,
                    "min_distance_angstrom": min_dist,
                    "max_distance_angstrom": max_dist,
                },
                files={"topology": topology_file, "trajectory": trajectory_file, "data": output_file},
                metadata={
                    "selection1": selection1,
                    "selection2": selection2,
                    "label1": label1,
                    "label2": label2,
                    "frame_interval": frame_interval,
                },
            )
        except Exception as exc:
            logger.warning("Failed to write min-distance summary: %s", exc)

    return {
        "success": True,
        "mean_distance": mean_dist,
        "std_distance": std_dist,
        "min_distance": min_dist,
        "max_distance": max_dist,
        "n_frames": len(distances),
        "selection1": selection1,
        "selection2": selection2,
        "label1": label1,
        "label2": label2,
        "output_file": output_file,
        "message": (
            f"Min heavy-atom distance ({label1} vs {label2}): "
            f"mean={mean_dist:.2f} Å, min={min_dist:.2f} Å"
        ),
    }


def compute_min_heavy_atom_distance_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    selection1: str,
    selection2: str,
    label1: str = "group1",
    label2: str = "group2",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    if not HAS_MDA or not HAS_NUMPY:
        return {"success": False, "error": "MDAnalysis and numpy are required for min-distance"}

    heavy1 = u.select_atoms(f"({selection1}) and not name H*")
    heavy2 = u.select_atoms(f"({selection2}) and not name H*")
    if len(heavy1) == 0:
        return {"success": False, "error": f"Selection 1 matched 0 heavy atoms: '{selection1}'"}
    if len(heavy2) == 0:
        return {"success": False, "error": f"Selection 2 matched 0 heavy atoms: '{selection2}'"}

    frames, times, distances = [], [], []
    interval = max(1, int(frame_interval or 1))
    for ts in u.trajectory[::interval]:
        dist = mda_distances.distance_array(
            heavy1.positions, heavy2.positions, box=getattr(ts, "dimensions", None)
        )
        if dist.size == 0:
            continue
        frames.append(int(ts.frame))
        times.append(float(ts.time))
        distances.append(float(np.min(dist)))

    return finalize_min_distance_result(
        frames, times, distances,
        selection1=selection1,
        selection2=selection2,
        label1=label1,
        label2=label2,
        output_file=output_file,
        topology_file=topology_file,
        trajectory_file=trajectory_file,
        working_dir=working_dir,
        frame_interval=interval,
    )


@tool
def calculate_min_heavy_atom_distance(
    topology_file: str,
    trajectory_file: str,
    selection1: str,
    selection2: str,
    label1: str = "group1",
    label2: str = "group2",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
    selection1_from_file: Optional[str] = None,
    selection2_from_file: Optional[str] = None,
    selection_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Per-frame minimum heavy-atom distance between two atom selections.

    Use for protein–protein (or any two-group) closest approach over time,
    e.g. chain B residues 1–34 vs chain A residues that were within 10 Å at
    frame 0. Not a protein–ligand contact counter.

    Args:
        topology_file: Topology file (.tpr, .gro, .pdb)
        trajectory_file: Trajectory file (.xtc, .trr)
        selection1: First MDAnalysis selection
        selection2: Second MDAnalysis selection
        label1: Label for selection 1
        label2: Label for selection 2
        output_file: CSV basename (overall: min_distance.csv; subset: min_distance_{qualifier}.csv)
        working_dir: Analysis output directory
        frame_interval: Process every Nth frame (default 1)
        selection1_from_file: Optional nearby_residues JSON/CSV for selection1
        selection2_from_file: Optional nearby_residues JSON/CSV for selection2
        selection_key: JSON key to read (default mda_selection_heavy)

    Returns:
        Dict with min-distance statistics and output path.

    Standard outputs: min_distance.csv, plot as min_distance.png.
    """
    original_dir = None
    try:
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)
        if not HAS_MDA or not HAS_NUMPY:
            return {
                "success": False,
                "error": "MDAnalysis and numpy are required for min heavy-atom distance",
            }
        if not os.path.exists(topology_file):
            return {"success": False, "error": f"Topology file not found: {topology_file}"}
        if not os.path.exists(trajectory_file):
            return {"success": False, "error": f"Trajectory file not found: {trajectory_file}"}

        params = apply_selection_from_files(
            {
                "selection1": selection1,
                "selection2": selection2,
                "selection1_from_file": selection1_from_file,
                "selection2_from_file": selection2_from_file,
                "selection_key": selection_key,
            },
            working_dir=working_dir,
        )

        u = mda.Universe(topology_file, trajectory_file)
        return compute_min_heavy_atom_distance_from_universe(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            selection1=params["selection1"],
            selection2=params["selection2"],
            label1=label1,
            label2=label2,
            output_file=output_file,
            working_dir=working_dir,
            frame_interval=frame_interval,
        )
    except Exception as exc:
        logger.exception("calculate_min_heavy_atom_distance failed")
        return {"success": False, "error": str(exc)}
    finally:
        if original_dir:
            os.chdir(original_dir)
