"""
Binding-site analysis for protein–ligand (e.g. protein–ATP) trajectories.

Tools:
  - ``calculate_protein_ligand_contacts`` — H-bonds + heavy-atom contact counts
  - ``calculate_pocket_sasa`` — SASA of catalytic pocket residues (subset)
  - ``analyze_ligand_residence`` — bound/unbound residence times and unbinding events
  - ``calculate_pocket_rmsf`` — per-residue RMSF for pocket Cα atoms
"""
from __future__ import annotations

import csv
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.analysis.pbc_utils import minimum_image_distance

import numpy as np
from langchain.tools import tool

from .summary_logger import append_analysis_summary

logger = logging.getLogger(__name__)

try:
    import MDAnalysis as mda
    from MDAnalysis.analysis.hydrogenbonds import HydrogenBondAnalysis
    from MDAnalysis.analysis import distances as mda_distances

    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    logger.warning("MDAnalysis not available — binding-site analysis disabled")


def identify_pocket_atoms(
    universe: "mda.Universe",
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    cutoff: float = 5.0,
) -> Tuple[Any, List[int], Dict[str, Any]]:
    """
    Pocket = protein atoms within *cutoff* Å of the ligand at frame 0.

    Returns (frozen AtomGroup, residue ids, metadata dict).
    """
    universe.trajectory[0]
    ligand = universe.select_atoms(ligand_selection)
    if len(ligand) == 0:
        raise ValueError(f"Ligand selection matched 0 atoms: '{ligand_selection}'")

    pocket_sel = f"({protein_selection}) and around {cutoff} ({ligand_selection})"
    pocket = universe.select_atoms(pocket_sel)
    if len(pocket) == 0:
        raise ValueError(
            f"No protein atoms within {cutoff} Å of ligand at frame 0. "
            "Check ligand resname or increase cutoff."
        )

    pocket_frozen = universe.atoms[pocket.indices]
    resids = sorted(set(int(r) for r in pocket_frozen.resids))
    meta = {
        "pocket_definition_mode": "ligand_proximity",
        "pocket_atom_count": len(pocket_frozen),
        "pocket_residue_count": len(resids),
        "pocket_resids": resids,
        "pocket_resnames": sorted(set(pocket_frozen.resnames)),
        "ligand_atom_count": len(ligand),
        "pocket_cutoff_A": float(cutoff),
    }
    return pocket_frozen, resids, meta


def resolve_pocket_atoms(
    universe: "mda.Universe",
    *,
    pocket_resids: Optional[List[int]] = None,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    pocket_cutoff: float = 5.0,
) -> Tuple[Any, List[int], Dict[str, Any]]:
    """
    Resolve pocket atoms either from an explicit residue list or ligand proximity.

    When ``pocket_resids`` is provided, all protein atoms in those residues
    define the pocket (consensus-mapped mode). Otherwise falls back to
    ``identify_pocket_atoms`` at frame 0.
    """
    if pocket_resids:
        universe.trajectory[0]
        resid_str = " ".join(str(int(r)) for r in pocket_resids)
        pocket_sel = f"({protein_selection}) and resid {resid_str}"
        pocket = universe.select_atoms(pocket_sel)
        if len(pocket) == 0:
            raise ValueError(
                f"No protein atoms matched consensus pocket resids: {pocket_resids[:12]}"
                + ("..." if len(pocket_resids) > 12 else "")
            )
        pocket_frozen = universe.atoms[pocket.indices]
        resids = sorted(set(int(r) for r in pocket_frozen.resids))
        meta = {
            "pocket_definition_mode": "consensus_resid_list",
            "pocket_atom_count": len(pocket_frozen),
            "pocket_residue_count": len(resids),
            "pocket_resids": resids,
            "pocket_resnames": sorted(set(pocket_frozen.resnames)),
            "requested_pocket_resids": [int(r) for r in pocket_resids],
        }
        return pocket_frozen, resids, meta
    return identify_pocket_atoms(
        universe, ligand_selection, protein_selection, pocket_cutoff
    )


def _write_gmx_index(path: str, group_name: str, atom_indices: np.ndarray) -> None:
    """Write a single-group GROMACS .ndx file (1-based atom numbers)."""
    one_based = (np.asarray(atom_indices, dtype=int) + 1).tolist()
    lines = [f"[ {group_name} ]\n"]
    for i in range(0, len(one_based), 15):
        lines.append(" ".join(str(x) for x in one_based[i : i + 15]) + "\n")
    Path(path).write_text("".join(lines), encoding="utf-8")


def _chdir_working(working_dir: Optional[str]) -> Optional[str]:
    if working_dir:
        os.makedirs(working_dir, exist_ok=True)
        original = os.getcwd()
        os.chdir(working_dir)
        return original
    return None


def _restore_cwd(original: Optional[str]) -> None:
    if original:
        os.chdir(original)


def _find_gmx() -> Optional[str]:
    import os
    import shutil

    candidates: list[str] = []
    for env_key in ("GMX", "GMX_BIN", "GROMACS_BIN"):
        val = os.environ.get(env_key, "").strip()
        if val:
            candidates.append(val)
    candidates.extend(("gmx", "gmx_mpi"))
    conda_prefix = os.environ.get("CONDA_PREFIX", "").strip()
    if conda_prefix:
        candidates.append(str(Path(conda_prefix) / "bin" / "gmx"))
    home = os.environ.get("HOME", "").strip()
    if home:
        candidates.append(f"{home}/conda_envs/SimAgentEnv/bin/gmx")

    seen: set[str] = set()
    for cmd in candidates:
        if not cmd or cmd in seen:
            continue
        seen.add(cmd)
        exe = cmd if os.path.sep in cmd else shutil.which(cmd)
        if not exe:
            continue
        try:
            r = subprocess.run([exe, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return exe
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            continue
    return None


def _parse_xvg_two_columns(path: str) -> Tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("@"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                xs.append(float(parts[0]))
                ys.append(float(parts[1]))
    return np.asarray(xs), np.asarray(ys)


def _debounce_bound_mask(
    bound_mask: Sequence[bool],
    *,
    min_run: int = 2,
) -> List[bool]:
    """Drop brief bound/unbound flips shorter than ``min_run`` frames."""
    if min_run <= 1 or len(bound_mask) < 3:
        return list(bound_mask)

    out = list(bound_mask)
    changed = True
    while changed:
        changed = False
        i = 0
        while i < len(out):
            j = i
            while j < len(out) and out[j] == out[i]:
                j += 1
            run_len = j - i
            if run_len < min_run and 0 < i and j < len(out):
                fill = out[i - 1]
                for k in range(i, j):
                    if out[k] != fill:
                        out[k] = fill
                        changed = True
            i = j
    return out


def _segment_residence(times_ns: np.ndarray, bound: np.ndarray) -> Dict[str, Any]:
    """Summarise bound/unbound segments from a boolean bound mask."""
    if len(bound) == 0:
        return {
            "fraction_bound": 0.0,
            "n_bound_events": 0,
            "n_unbinding_events": 0,
            "longest_bound_ns": 0.0,
            "mean_bound_event_ns": 0.0,
            "longest_unbound_ns": 0.0,
        }

    bound_events: List[float] = []
    unbound_events: List[float] = []
    n_unbinding = 0
    n_rebinding = 0

    in_bound = bool(bound[0])
    seg_start = 0
    for i in range(1, len(bound)):
        if bound[i] != bound[i - 1]:
            dt = float(times_ns[i] - times_ns[seg_start])
            if in_bound:
                bound_events.append(dt)
                n_unbinding += 1
            else:
                unbound_events.append(dt)
                n_rebinding += 1
            seg_start = i
            in_bound = bool(bound[i])

    dt = float(times_ns[-1] - times_ns[seg_start])
    if in_bound:
        bound_events.append(dt)
    else:
        unbound_events.append(dt)

    if bound[0]:
        n_rebinding = max(0, n_rebinding)
    else:
        n_unbinding = max(0, n_unbinding)

    return {
        "fraction_bound": float(np.mean(bound)),
        "n_bound_events": len(bound_events),
        "n_unbinding_events": n_unbinding,
        "n_rebinding_events": n_rebinding,
        "longest_bound_ns": float(max(bound_events) if bound_events else 0.0),
        "mean_bound_event_ns": float(np.mean(bound_events) if bound_events else 0.0),
        "longest_unbound_ns": float(max(unbound_events) if unbound_events else 0.0),
        "bound_events_ns": bound_events,
        "unbound_events_ns": unbound_events,
    }


def compute_protein_ligand_contacts_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    contact_cutoff: float = 4.0,
    hbond_distance: float = 3.0,
    hbond_angle: float = 150.0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
    pocket_resids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Protein–ligand contacts from a pre-loaded Universe."""
    contact_protein_selection = protein_selection
    if pocket_resids:
        _, resids, _ = resolve_pocket_atoms(
            u, pocket_resids=pocket_resids, protein_selection=protein_selection
        )
        resid_str = " ".join(str(r) for r in resids)
        contact_protein_selection = f"({protein_selection}) and resid {resid_str}"
        protein = u.select_atoms(contact_protein_selection)
    else:
        protein = u.select_atoms(protein_selection)
    ligand = u.select_atoms(ligand_selection)
    if len(protein) == 0 or len(ligand) == 0:
        return {"success": False, "error": "Protein or ligand selection is empty"}

    protein_heavy = protein.select_atoms("not name H*")
    ligand_heavy = ligand.select_atoms("not name H*")
    step = max(1, int(frame_interval))

    hbonds = HydrogenBondAnalysis(
        u,
        donors_sel=f"({contact_protein_selection}) or ({ligand_selection})",
        acceptors_sel=f"({contact_protein_selection}) or ({ligand_selection})",
        between=[contact_protein_selection, ligand_selection],
        d_a_cutoff=float(hbond_distance),
        d_h_a_angle_cutoff=float(hbond_angle),
    )
    hbonds.run(step=step)

    hbond_by_frame: Dict[int, int] = {}
    if hbonds.results.hbonds is not None and len(hbonds.results.hbonds):
        for row in hbonds.results.hbonds:
            frame_idx = int(row[0])
            hbond_by_frame[frame_idx] = hbond_by_frame.get(frame_idx, 0) + 1

    rows: List[List[Any]] = []
    contact_counts: List[int] = []
    hbond_counts: List[int] = []

    for ts in u.trajectory[::step]:
        frame_i = ts.frame
        n_h = hbond_by_frame.get(frame_i, 0)
        dist_arr = mda_distances.distance_array(
            protein_heavy.positions,
            ligand_heavy.positions,
            box=getattr(ts, "dimensions", None),
        )
        n_contacts = int(np.sum(dist_arr <= float(contact_cutoff)))
        rows.append([frame_i, ts.time / 1000.0, n_h, n_contacts])
        hbond_counts.append(n_h)
        contact_counts.append(n_contacts)

    out = output_file or "protein_ligand_contacts.csv"
    with open(out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["frame", "time_ns", "n_hbonds", "n_contacts"])
        writer.writerows(rows)

    stats = {
        "mean_hbonds": float(np.mean(hbond_counts)) if hbond_counts else 0.0,
        "max_hbonds": int(max(hbond_counts)) if hbond_counts else 0,
        "mean_contacts": float(np.mean(contact_counts)) if contact_counts else 0.0,
        "max_contacts": int(max(contact_counts)) if contact_counts else 0,
        "frames_with_hbonds": int(sum(1 for x in hbond_counts if x > 0)),
        "frames_with_contacts": int(sum(1 for x in contact_counts if x > 0)),
    }

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="ProteinLigandContacts",
                statistics=stats,
                files={"csv": out, "topology": topology_file, "trajectory": trajectory_file},
                metadata={
                    "ligand_selection": ligand_selection,
                    "contact_cutoff_A": contact_cutoff,
                    "pocket_resids": pocket_resids[:20] if pocket_resids else None,
                    "pocket_restricted": bool(pocket_resids),
                },
            )
        except Exception as exc:
            logger.warning("Summary log failed: %s", exc)

    return {
        "success": True,
        "message": (
            f"Contacts: mean {stats['mean_contacts']:.1f} pairs/frame, "
            f"H-bonds: mean {stats['mean_hbonds']:.2f}/frame"
        ),
        "output_file": out,
        **stats,
    }


def finalize_ligand_residence_result(
    times_ns: list,
    bound_mask: list,
    min_dists: list,
    *,
    bound_distance_A: float,
    min_contacts: int,
    pocket_meta: Dict[str, Any],
    output_file: Optional[str],
    working_dir: Optional[str],
) -> Dict[str, Any]:
    """Write residence CSV/JSON and return result dict from fused streaming data."""
    import json as _json

    times_arr = np.asarray(times_ns)
    bound = np.asarray(bound_mask, dtype=bool)
    residence = _segment_residence(times_arr, bound)

    csv_out = output_file or "ligand_residence.csv"
    if working_dir and not Path(csv_out).is_absolute():
        out_dir = Path(working_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_out = str(out_dir / Path(csv_out).name)
    with open(csv_out, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["time_ns", "bound", "min_contact_distance_A", "n_like_bound"])
        for t, b, d in zip(times_ns, bound_mask, min_dists):
            writer.writerow([f"{float(t):.6f}", int(b), f"{float(d):.4f}", int(b)])

    json_out = str(Path(csv_out).with_suffix(".json"))
    summary = {
        **residence,
        "bound_distance_A": bound_distance_A,
        "min_contacts": min_contacts,
        "pocket_residue_count": pocket_meta.get("pocket_residue_count", 0),
    }
    if "bound_mode" in pocket_meta:
        summary["bound_mode"] = pocket_meta["bound_mode"]
    summary.pop("bound_events_ns", None)
    summary.pop("unbound_events_ns", None)
    Path(json_out).write_text(_json.dumps(summary, indent=2), encoding="utf-8")

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="LigandResidence",
                statistics=summary,
                files={"csv": csv_out, "json": json_out},
            )
        except Exception as exc:
            logger.warning("Summary log failed: %s", exc)

    return {
        "success": True,
        "message": (
            f"Bound {residence['fraction_bound'] * 100:.1f}% of trajectory; "
            f"{residence['n_unbinding_events']} unbinding event(s); "
            f"longest bound {residence['longest_bound_ns']:.1f} ns"
        ),
        "output_file": csv_out,
        "output_json": json_out,
        **summary,
    }


def compute_ligand_residence_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    pocket_cutoff: float = 5.0,
    bound_distance_A: float = 5.0,
    min_contacts: int = 1,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
    pocket_resids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Ligand residence analysis from a pre-loaded Universe."""
    pocket, _, meta = resolve_pocket_atoms(
        u,
        pocket_resids=pocket_resids,
        ligand_selection=ligand_selection,
        protein_selection=protein_selection,
        pocket_cutoff=pocket_cutoff,
    )
    ligand = u.select_atoms(ligand_selection)
    if pocket_resids:
        resid_str = " ".join(str(r) for r in meta.get("pocket_resids", pocket_resids))
        protein_heavy = u.select_atoms(
            f"({protein_selection}) and resid {resid_str} and not name H*"
        )
    else:
        protein_heavy = u.select_atoms(f"({protein_selection}) and not name H*")
    ligand_heavy = ligand.select_atoms("not name H*")

    times: List[float] = []
    bound_mask: List[bool] = []
    min_dists: List[float] = []
    step = max(1, int(frame_interval))

    box = None
    for ts in u.trajectory[::step]:
        # Trust already-wrapped trajectories; do not re-wrap pocket/ligand
        # residue-by-residue before COM (breaks large pocket COMs).
        box = getattr(ts, "dimensions", None)
        pocket_com = pocket.center_of_mass()
        lig_com = ligand.center_of_mass()
        com_dist = minimum_image_distance(pocket_com, lig_com, box)
        dist_arr = mda_distances.distance_array(
            protein_heavy.positions,
            ligand_heavy.positions,
            box=box,
        )
        n_contacts = int(np.sum(dist_arr <= bound_distance_A))
        min_d = float(np.min(dist_arr)) if dist_arr.size else com_dist
        is_bound = (n_contacts >= int(min_contacts)) or (com_dist <= bound_distance_A)
        times.append(ts.time / 1000.0)
        bound_mask.append(is_bound)
        min_dists.append(min_d)

    bound_mask = _debounce_bound_mask(bound_mask, min_run=2)

    return finalize_ligand_residence_result(
        times,
        bound_mask,
        min_dists,
        bound_distance_A=bound_distance_A,
        min_contacts=min_contacts,
        pocket_meta=meta,
        output_file=output_file,
        working_dir=working_dir,
    )


def compute_pocket_rmsf_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    pocket_cutoff: float = 5.0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_trajectory: bool = True,
    skip_align: bool = False,
    pocket_resids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """Pocket RMSF from a pre-loaded (typically aligned) Universe."""
    from MDAnalysis.analysis import align, rms

    _, resids, meta = resolve_pocket_atoms(
        u,
        pocket_resids=pocket_resids,
        ligand_selection=ligand_selection,
        protein_selection=protein_selection,
        pocket_cutoff=pocket_cutoff,
    )
    resid_str = " ".join(str(r) for r in resids)
    pocket_ca_sel = f"protein and name CA and resid {resid_str}"
    pocket_ca = u.select_atoms(pocket_ca_sel)
    if len(pocket_ca) == 0:
        return {"success": False, "error": f"No pocket Cα atoms for resid {resid_str}"}

    if align_trajectory and not skip_align:
        align.AlignTraj(u, u, select="protein and name CA", in_memory=True).run()

    rmsf_calc = rms.RMSF(pocket_ca)
    rmsf_calc.run()
    rmsf_vals = rmsf_calc.results.rmsf

    out = output_file or "pocket_rmsf.dat"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("# Residue\tResName\tRMSF(Angstrom)\n")
        for res, val in zip(pocket_ca.residues, rmsf_vals):
            fh.write(f"{res.resid}\t{res.resname}\t{float(val):.4f}\n")

    stats = {
        "mean_pocket_rmsf": float(np.mean(rmsf_vals)),
        "max_pocket_rmsf": float(np.max(rmsf_vals)),
        "min_pocket_rmsf": float(np.min(rmsf_vals)),
        "pocket_residue_count": len(resids),
    }

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="PocketRMSF",
                statistics=stats,
                files={"dat": out, "topology": topology_file, "trajectory": trajectory_file},
                metadata={"pocket_resids": resids[:20], "pre_aligned_universe": skip_align},
            )
        except Exception as exc:
            logger.warning("Summary log failed: %s", exc)

    return {
        "success": True,
        "message": f"Pocket RMSF ({len(resids)} residues): mean={stats['mean_pocket_rmsf']:.2f} Å",
        "output_file": out,
        **stats,
    }


def compute_ligand_rmsf_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    output_file: Optional[str] = None,
    output_json: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_trajectory: bool = True,
    align_selection: Optional[str] = None,
    skip_align: bool = False,
) -> Dict[str, Any]:
    """Ligand RMSF from a pre-loaded (typically aligned) Universe."""
    import json as _json
    from MDAnalysis.analysis import align, rms

    ligand = u.select_atoms(f"({ligand_selection}) and not name H*")
    if len(ligand) == 0:
        ligand = u.select_atoms(ligand_selection)
    if len(ligand) == 0:
        return {"success": False, "error": f"Ligand selection empty: '{ligand_selection}'"}

    align_sel = align_selection or f"{protein_selection} and name CA"
    if align_trajectory and not skip_align:
        align.AlignTraj(u, u, select=align_sel, in_memory=True).run()

    rmsf_calc = rms.RMSF(ligand)
    rmsf_calc.run()
    rmsf_vals = np.asarray(rmsf_calc.results.rmsf, dtype=float)

    out = output_file or "ligand_rmsf.dat"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write("# AtomIndex\tAtomName\tResName\tResid\tRMSF(Angstrom)\n")
        for atom, val in zip(ligand, rmsf_vals):
            fh.write(
                f"{atom.index}\t{atom.name}\t{atom.resname}\t{atom.resid}\t{float(val):.4f}\n"
            )

    stats = {
        "mean_ligand_rmsf": float(np.mean(rmsf_vals)),
        "std_ligand_rmsf": float(np.std(rmsf_vals)),
        "max_ligand_rmsf": float(np.max(rmsf_vals)),
        "min_ligand_rmsf": float(np.min(rmsf_vals)),
        "n_ligand_atoms": len(ligand),
        "ligand_resname": ligand.resnames[0] if len(ligand) else "",
    }

    json_out = output_json or "ligand_rmsf.json"
    Path(json_out).write_text(_json.dumps(stats, indent=2), encoding="utf-8")

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="LigandRMSF",
                statistics=stats,
                files={"dat": out, "json": json_out, "topology": topology_file, "trajectory": trajectory_file},
                metadata={"ligand_selection": ligand_selection, "pre_aligned_universe": skip_align},
            )
        except Exception as exc:
            logger.warning("Summary log failed: %s", exc)

    return {
        "success": True,
        "message": f"Ligand RMSF ({stats['n_ligand_atoms']} atoms): mean={stats['mean_ligand_rmsf']:.2f} Å",
        "output_file": out,
        "output_json": json_out,
        **stats,
    }


@tool
def calculate_protein_ligand_contacts(
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    contact_cutoff: float = 4.0,
    hbond_distance: float = 3.0,
    hbond_angle: float = 150.0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    """
    Count protein–ligand hydrogen bonds and heavy-atom contacts per frame.

    **H-bonds:** MDAnalysis ``HydrogenBondAnalysis`` between protein and ligand
    (donor–H···acceptor distance ≤ ``hbond_distance`` Å, angle ≥ ``hbond_angle``°).

    **Contacts:** number of unique protein heavy-atom ↔ ligand heavy-atom pairs
    with distance ≤ ``contact_cutoff`` Å.

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr).
        trajectory_file: Trajectory file (.xtc, .trr, .dcd).
        ligand_selection: Ligand selection string (default ``"resname ATP"``).
        protein_selection: Protein selection string (default ``"protein"``).
        contact_cutoff: Heavy-atom contact cutoff in Å.
        hbond_distance: H-bond donor-acceptor cutoff in Å.
        hbond_angle: H-bond angle cutoff in degrees.
        output_file: Output CSV filename.
        working_dir: Working directory for outputs.
        frame_interval: Process every Nth trajectory frame.

    Returns:
        Dict with contact/h-bond statistics and output CSV path.

    Standard output: ``protein_ligand_contacts.csv``.
    """
    original = _chdir_working(working_dir)
    try:
        if not HAS_MDA:
            return {"success": False, "error": "MDAnalysis is required"}

        if not os.path.isfile(topology_file) or not os.path.isfile(trajectory_file):
            return {"success": False, "error": "Topology or trajectory file not found"}

        u = mda.Universe(topology_file, trajectory_file)
        return compute_protein_ligand_contacts_from_universe(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            ligand_selection=ligand_selection,
            protein_selection=protein_selection,
            contact_cutoff=contact_cutoff,
            hbond_distance=hbond_distance,
            hbond_angle=hbond_angle,
            output_file=output_file,
            working_dir=working_dir,
            frame_interval=frame_interval,
        )
    except Exception as exc:
        logger.exception("protein_ligand_contacts failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original)


@tool
def calculate_pocket_sasa(
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    pocket_cutoff: float = 5.0,
    probe_radius: float = 0.14,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Solvent-accessible surface area (SASA) of the ATP binding pocket subset.

    Pocket residues are defined at frame 0 as protein atoms within
    ``pocket_cutoff`` Å of the ligand (same definition as ligand-pocket distance).
    Uses GROMACS ``gmx sasa`` with a generated index group when a ``.tpr`` is
    available; otherwise reports an error asking for a TPR topology.

    SASA measures how exposed the pocket is to solvent — lower SASA often
    indicates a more buried / closed binding site.

    Args:
        topology_file: Topology file (must be a ``.tpr`` for gmx sasa workflow).
        trajectory_file: Trajectory file (.xtc/.trr).
        ligand_selection: Ligand selection used to define the pocket.
        protein_selection: Protein selection used to define nearby pocket atoms.
        pocket_cutoff: Pocket definition cutoff in Å from ligand atoms.
        probe_radius: Solvent probe radius in nm.
        output_file: Output CSV filename.
        working_dir: Working directory for outputs.

    Returns:
        Dict with pocket SASA statistics and output CSV path.

    Standard output: ``pocket_sasa.csv`` (time_ns, sasa_nm2).
    """
    original = _chdir_working(working_dir)
    ndx_path = "pocket_sasa.ndx"
    xvg_path = "pocket_sasa.xvg"
    try:
        if not HAS_MDA:
            return {"success": False, "error": "MDAnalysis is required"}

        gmx = _find_gmx()
        if not gmx:
            return {"success": False, "error": "GROMACS (gmx) not found in PATH"}

        tpr = topology_file if topology_file.endswith(".tpr") else None
        if not tpr or not os.path.isfile(tpr):
            return {
                "success": False,
                "error": (
                    "Pocket SASA requires a GROMACS .tpr topology file. "
                    f"Got: {topology_file}"
                ),
            }
        if not os.path.isfile(trajectory_file):
            return {"success": False, "error": f"Trajectory not found: {trajectory_file}"}

        u = mda.Universe(tpr, trajectory_file)
        pocket, resids, meta = resolve_pocket_atoms(
            u,
            pocket_resids=None,
            ligand_selection=ligand_selection,
            protein_selection=protein_selection,
            pocket_cutoff=pocket_cutoff,
        )
        _write_gmx_index(ndx_path, "Pocket", pocket.indices)

        cmd = [
            gmx, "sasa",
            "-f", trajectory_file,
            "-s", tpr,
            "-n", ndx_path,
            "-o", xvg_path,
            "-probe", str(probe_radius),
        ]
        proc = subprocess.run(
            cmd,
            input="Pocket\nPocket\n",
            capture_output=True,
            text=True,
            timeout=600,
        )
        if proc.returncode != 0:
            return {"success": False, "error": f"gmx sasa failed: {proc.stderr[:400]}"}

        times_ps, sasa_nm2 = _parse_xvg_two_columns(xvg_path)
        if len(sasa_nm2) == 0:
            return {"success": False, "error": "No SASA data in gmx output"}

        out = output_file or "pocket_sasa.csv"
        with open(out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["time_ns", "pocket_sasa_nm2"])
            for t, s in zip(times_ps / 1000.0, sasa_nm2):
                writer.writerow([f"{t:.6f}", f"{s:.6f}"])

        stats = {
            "mean_pocket_sasa_nm2": float(np.mean(sasa_nm2)),
            "std_pocket_sasa_nm2": float(np.std(sasa_nm2)),
            "min_pocket_sasa_nm2": float(np.min(sasa_nm2)),
            "max_pocket_sasa_nm2": float(np.max(sasa_nm2)),
            **meta,
        }

        if working_dir:
            try:
                append_analysis_summary(
                    working_dir=working_dir,
                    analysis_type="PocketSASA",
                    statistics=stats,
                    files={"csv": out},
                    metadata={"pocket_cutoff_A": pocket_cutoff},
                )
            except Exception as exc:
                logger.warning("Summary log failed: %s", exc)

        return {
            "success": True,
            "message": (
                f"Pocket SASA ({meta['pocket_residue_count']} residues): "
                f"mean={stats['mean_pocket_sasa_nm2']:.2f} nm²"
            ),
            "output_file": out,
            **stats,
        }
    except Exception as exc:
        logger.exception("pocket_sasa failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original)


@tool
def analyze_ligand_residence(
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    pocket_cutoff: float = 5.0,
    bound_distance_A: float = 5.0,
    min_contacts: int = 1,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    """
    Estimate ligand residence time and unbinding/rebinding events.

    **Bound criterion (per frame):** ligand heavy atoms have ≥ ``min_contacts``
    protein heavy-atom contacts within ``bound_distance_A`` Å **or** ligand COM is
    within ``bound_distance_A`` Å of the frame-0 pocket COM.

    Reports:
      - fraction of trajectory spent bound
      - number of unbinding events (bound → unbound transitions)
      - longest continuous bound residence (ns)
      - mean bound-event duration

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr).
        trajectory_file: Trajectory file (.xtc, .trr, .dcd).
        ligand_selection: Ligand selection string (default ``"resname ATP"``).
        protein_selection: Protein selection string (default ``"protein"``).
        pocket_cutoff: Pocket-definition cutoff in Å.
        bound_distance_A: Bound-state cutoff distance in Å.
        min_contacts: Minimum heavy-atom contacts to classify as bound.
        output_file: Output CSV filename for per-frame bound state.
        working_dir: Working directory for outputs.
        frame_interval: Process every Nth trajectory frame.

    Returns:
        Dict with residence metrics and output file paths.

    Standard outputs: ``ligand_residence.csv``, ``ligand_residence.json``.
    """
    import json as _json

    original = _chdir_working(working_dir)
    try:
        if not HAS_MDA:
            return {"success": False, "error": "MDAnalysis is required"}

        u = mda.Universe(topology_file, trajectory_file)
        return compute_ligand_residence_from_universe(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            ligand_selection=ligand_selection,
            protein_selection=protein_selection,
            pocket_cutoff=pocket_cutoff,
            bound_distance_A=bound_distance_A,
            min_contacts=min_contacts,
            output_file=output_file,
            working_dir=working_dir,
            frame_interval=frame_interval,
        )
    except Exception as exc:
        logger.exception("ligand_residence failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original)


@tool
def calculate_pocket_rmsf(
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    pocket_cutoff: float = 5.0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_trajectory: bool = True,
) -> Dict[str, Any]:
    """
    Per-residue RMSF for binding-pocket Cα atoms only.

    Pocket residues are identified at frame 0 (within ``pocket_cutoff`` Å of
    ligand). Trajectory is aligned on protein Cα before computing RMSF:

        RMSF_i = √(⟨|r_i(t) − ⟨r_i⟩|²⟩)

    Higher pocket RMSF → more flexible binding site; useful for comparing
    rigid vs dynamic pockets across the 35 protein–ATP systems.

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr).
        trajectory_file: Trajectory file (.xtc, .trr, .dcd).
        ligand_selection: Ligand selection used for pocket definition.
        protein_selection: Protein selection used for pocket definition.
        pocket_cutoff: Pocket-definition cutoff in Å.
        output_file: Output data filename.
        working_dir: Working directory for outputs.
        align_trajectory: Align trajectory on protein Cα before RMSF.

    Returns:
        Dict with pocket RMSF statistics and output file path.

    Standard output: ``pocket_rmsf.dat``.
    """
    original = _chdir_working(working_dir)
    try:
        if not HAS_MDA:
            return {"success": False, "error": "MDAnalysis is required"}

        u = mda.Universe(topology_file, trajectory_file)
        return compute_pocket_rmsf_from_universe(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            ligand_selection=ligand_selection,
            protein_selection=protein_selection,
            pocket_cutoff=pocket_cutoff,
            output_file=output_file,
            working_dir=working_dir,
            align_trajectory=align_trajectory,
        )
    except Exception as exc:
        logger.exception("pocket_rmsf failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original)


@tool
def calculate_ligand_rmsf(
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname ATP",
    protein_selection: str = "protein",
    output_file: Optional[str] = None,
    output_json: Optional[str] = None,
    working_dir: Optional[str] = None,
    align_trajectory: bool = True,
    align_selection: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Per-atom RMSF of the ligand (ATP) after aligning the trajectory on protein Cα.

    Measures ligand flexibility relative to the protein frame — useful for
    classification alongside pocket RMSF and residence time:

        RMSF_i = √(⟨|r_i(t) − ⟨r_i⟩|²⟩)

    **Default:** heavy atoms only (excludes hydrogens). Trajectory is aligned on
    ``protein and name CA`` before RMSF so ligand motion reflects internal
    flexibility + binding-site motion, not global translation/rotation.

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr).
        trajectory_file: Trajectory file (.xtc, .trr, .dcd).
        ligand_selection: Ligand selection string (default ``"resname ATP"``).
        protein_selection: Protein selection used for alignment context.
        output_file: Output data filename.
        output_json: Output JSON summary filename.
        working_dir: Working directory for outputs.
        align_trajectory: Align trajectory before RMSF calculation.
        align_selection: Explicit selection for alignment step.

    Returns:
        Dict with ligand RMSF statistics and output artifact paths.

    Standard outputs: ``ligand_rmsf.dat``, ``ligand_rmsf.json`` (summary stats).
    """
    import json as _json

    original = _chdir_working(working_dir)
    try:
        if not HAS_MDA:
            return {"success": False, "error": "MDAnalysis is required"}

        u = mda.Universe(topology_file, trajectory_file)
        return compute_ligand_rmsf_from_universe(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            ligand_selection=ligand_selection,
            protein_selection=protein_selection,
            output_file=output_file,
            output_json=output_json,
            working_dir=working_dir,
            align_trajectory=align_trajectory,
            align_selection=align_selection,
        )
    except Exception as exc:
        logger.exception("ligand_rmsf failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original)
