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
from typing import Any, Dict, List, Optional, Tuple

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
        "pocket_atom_count": len(pocket_frozen),
        "pocket_residue_count": len(resids),
        "pocket_resids": resids,
        "pocket_resnames": sorted(set(pocket_frozen.resnames)),
        "ligand_atom_count": len(ligand),
    }
    return pocket_frozen, resids, meta


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
    for cmd in ("gmx", "gmx_mpi"):
        try:
            r = subprocess.run([cmd, "--version"], capture_output=True, timeout=5)
            if r.returncode == 0:
                return cmd
        except (FileNotFoundError, subprocess.TimeoutExpired):
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
        protein = u.select_atoms(protein_selection)
        ligand = u.select_atoms(ligand_selection)
        if len(protein) == 0 or len(ligand) == 0:
            return {"success": False, "error": "Protein or ligand selection is empty"}

        protein_heavy = protein.select_atoms("not name H*")
        ligand_heavy = ligand.select_atoms("not name H*")

        # H-bonds across protein ↔ ligand
        hbonds = HydrogenBondAnalysis(
            u,
            donors_sel=f"({protein_selection}) or ({ligand_selection})",
            acceptors_sel=f"({protein_selection}) or ({ligand_selection})",
            between=[protein_selection, ligand_selection],
            d_a_cutoff=float(hbond_distance),
            d_h_a_angle_cutoff=float(hbond_angle),
        )
        hbonds.run(step=max(1, int(frame_interval)))

        hbond_by_frame: Dict[int, int] = {}
        if hbonds.results.hbonds is not None and len(hbonds.results.hbonds):
            for row in hbonds.results.hbonds:
                frame_idx = int(row[0])
                hbond_by_frame[frame_idx] = hbond_by_frame.get(frame_idx, 0) + 1

        rows: List[List[Any]] = []
        contact_counts: List[int] = []
        hbond_counts: List[int] = []

        for ts in u.trajectory[:: max(1, int(frame_interval))]:
            frame_i = ts.frame
            n_h = hbond_by_frame.get(frame_i, 0)
            dist_arr = mda_distances.distance_array(
                protein_heavy.positions,
                ligand_heavy.positions,
            )
            n_contacts = int(np.sum(dist_arr <= float(contact_cutoff)))
            t_ns = ts.time / 1000.0
            rows.append([frame_i, t_ns, n_h, n_contacts])
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
                    files={"csv": out},
                    metadata={
                        "ligand_selection": ligand_selection,
                        "contact_cutoff_A": contact_cutoff,
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
        pocket, resids, meta = identify_pocket_atoms(
            u, ligand_selection, protein_selection, pocket_cutoff
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
        pocket, _, meta = identify_pocket_atoms(
            u, ligand_selection, protein_selection, pocket_cutoff
        )
        ligand = u.select_atoms(ligand_selection)
        protein_heavy = u.select_atoms(f"({protein_selection}) and not name H*")
        ligand_heavy = ligand.select_atoms("not name H*")

        times: List[float] = []
        bound_mask: List[bool] = []
        min_dists: List[float] = []

        for ts in u.trajectory[:: max(1, int(frame_interval))]:
            pocket_com = pocket.center_of_mass()
            lig_com = ligand.center_of_mass()
            com_dist = float(np.linalg.norm(lig_com - pocket_com))
            dist_arr = mda_distances.distance_array(
                protein_heavy.positions,
                ligand_heavy.positions,
            )
            n_contacts = int(np.sum(dist_arr <= bound_distance_A))
            min_d = float(np.min(dist_arr)) if dist_arr.size else com_dist
            is_bound = (n_contacts >= int(min_contacts)) or (com_dist <= bound_distance_A)
            times.append(ts.time / 1000.0)
            bound_mask.append(is_bound)
            min_dists.append(min_d)

        times_ns = np.asarray(times)
        bound = np.asarray(bound_mask, dtype=bool)
        residence = _segment_residence(times_ns, bound)

        csv_out = output_file or "ligand_residence.csv"
        with open(csv_out, "w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(["time_ns", "bound", "min_contact_distance_A", "n_like_bound"])
            for t, b, d in zip(times, bound_mask, min_dists):
                writer.writerow([f"{t:.6f}", int(b), f"{d:.4f}", int(b)])

        json_out = "ligand_residence.json"
        summary = {
            **residence,
            "bound_distance_A": bound_distance_A,
            "min_contacts": min_contacts,
            "pocket_residue_count": meta["pocket_residue_count"],
        }
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

        from MDAnalysis.analysis import align, rms

        u = mda.Universe(topology_file, trajectory_file)
        _, resids, meta = identify_pocket_atoms(
            u, ligand_selection, protein_selection, pocket_cutoff
        )

        resid_str = " ".join(str(r) for r in resids)
        pocket_ca_sel = f"protein and name CA and resid {resid_str}"
        pocket_ca = u.select_atoms(pocket_ca_sel)
        if len(pocket_ca) == 0:
            return {"success": False, "error": f"No pocket Cα atoms for resid {resid_str}"}

        align_sel = u.select_atoms("protein and name CA")
        if align_trajectory:
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
                    files={"dat": out},
                    metadata={"pocket_resids": resids[:20]},
                )
            except Exception as exc:
                logger.warning("Summary log failed: %s", exc)

        return {
            "success": True,
            "message": (
                f"Pocket RMSF ({len(resids)} residues): "
                f"mean={stats['mean_pocket_rmsf']:.2f} Å"
            ),
            "output_file": out,
            **stats,
        }
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

        from MDAnalysis.analysis import align, rms

        u = mda.Universe(topology_file, trajectory_file)
        ligand = u.select_atoms(f"({ligand_selection}) and not name H*")
        if len(ligand) == 0:
            ligand = u.select_atoms(ligand_selection)
        if len(ligand) == 0:
            return {"success": False, "error": f"Ligand selection empty: '{ligand_selection}'"}

        align_sel = align_selection or f"{protein_selection} and name CA"
        if align_trajectory:
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
                    files={"dat": out, "json": json_out},
                    metadata={"ligand_selection": ligand_selection},
                )
            except Exception as exc:
                logger.warning("Summary log failed: %s", exc)

        return {
            "success": True,
            "message": (
                f"Ligand RMSF ({stats['n_ligand_atoms']} atoms): "
                f"mean={stats['mean_ligand_rmsf']:.2f} Å"
            ),
            "output_file": out,
            "output_json": json_out,
            **stats,
        }
    except Exception as exc:
        logger.exception("ligand_rmsf failed")
        return {"success": False, "error": str(exc)}
    finally:
        _restore_cwd(original)
