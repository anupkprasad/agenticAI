"""
COM Distance Calculator - Center-of-Mass distance between two selections

Computes per-frame Euclidean distance between the center of mass of two
arbitrary MDAnalysis atom selections over an MD trajectory.

Use cases:
  - Protein domain–domain distance
  - Protein–ligand distance
  - Ligand–ion distance
  - Any two groups of atoms
"""
import json
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from langchain.tools import tool
from .summary_logger import append_analysis_summary
from .pbc_utils import minimum_image_distance, clean_pbc_distance_series

logger = logging.getLogger(__name__)

# Optional dependencies
try:
    import MDAnalysis as mda
    HAS_MDA = True
except ImportError:
    HAS_MDA = False
    logger.warning("MDAnalysis not available - COM distance calculation will be limited")

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


def finalize_com_distance_result(
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
        return {"success": False, "error": "No COM distance values collected"}

    distances_arr = np.array(distances)
    mean_dist = float(np.mean(distances_arr))
    std_dist = float(np.std(distances_arr))
    min_dist = float(np.min(distances_arr))
    max_dist = float(np.max(distances_arr))

    if not output_file:
        safe1 = label1.replace(" ", "_")
        safe2 = label2.replace(" ", "_")
        output_file = f"com_distance_{safe1}_vs_{safe2}.csv"

    with open(output_file, "w") as f:
        f.write("frame,time_ns,distance_angstrom\n")
        for fr, t, d in zip(frames, times, distances):
            f.write(f"{fr},{t/1000.0:.4f},{d:.4f}\n")

    analysis_type = f"INTER_COM_Distance_{label1}_vs_{label2}"
    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type=analysis_type,
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
        except Exception as e:
            logger.warning(f"Failed to write to summary file: {e}")

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
            f"COM distance ({label1} vs {label2}): "
            f"mean={mean_dist:.2f} Å, std={std_dist:.2f} Å"
        ),
    }


def compute_com_distance_from_universe(
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
        return {"success": False, "error": "MDAnalysis and numpy are required for COM distance"}

    group1 = u.select_atoms(selection1)
    group2 = u.select_atoms(selection2)
    if len(group1) == 0:
        return {"success": False, "error": f"Selection 1 matched 0 atoms: '{selection1}'"}
    if len(group2) == 0:
        return {"success": False, "error": f"Selection 2 matched 0 atoms: '{selection2}'"}

    frames, times, distances = [], [], []
    for ts in u.trajectory[::frame_interval]:
        # Trust already-wrapped trajectories (e.g. mdWrap.xtc). Do not
        # AtomGroup.wrap(compound="residues") before COM — that can scatter a
        # multi-residue pocket across images and inflate COM–COM distances.
        dist = minimum_image_distance(
            group1.center_of_mass(), group2.center_of_mass(), getattr(ts, "dimensions", None)
        )
        frames.append(int(ts.frame))
        times.append(float(ts.time))
        distances.append(dist)

    # Remove residual transient PBC spikes so stats/plots are not corrupted.
    cleaned, _, n_removed = clean_pbc_distance_series(distances)
    if n_removed:
        logger.info("COM distance (%s vs %s): removed %d PBC spike(s)", label1, label2, n_removed)
        distances = [float(v) for v in cleaned]

    return finalize_com_distance_result(
        frames, times, distances,
        selection1=selection1,
        selection2=selection2,
        label1=label1,
        label2=label2,
        output_file=output_file,
        topology_file=topology_file,
        trajectory_file=trajectory_file,
        working_dir=working_dir,
        frame_interval=frame_interval,
    )


def finalize_ligand_pocket_distance_result(
    frames: list,
    times: list,
    distances: list,
    *,
    ligand_selection: str,
    protein_selection: str,
    cutoff: float,
    pocket_resids: list,
    n_pocket_atoms: int,
    output_file: Optional[str],
    topology_file: str,
    trajectory_file: str,
    working_dir: Optional[str],
) -> Dict[str, Any]:
    if not distances:
        return {"success": False, "error": "No ligand pocket distance values collected"}

    distances_arr = np.array(distances)
    mean_dist = float(np.mean(distances_arr))
    std_dist = float(np.std(distances_arr))
    min_dist = float(np.min(distances_arr))
    max_dist = float(np.max(distances_arr))

    if not output_file:
        lig_tag = ligand_selection.replace(" ", "_")
        output_file = f"ligand_pocket_distance_{lig_tag}_cutoff{int(cutoff)}A.csv"

    with open(output_file, "w") as fh:
        fh.write("frame,time_ns,distance_angstrom\n")
        for fr, t, d in zip(frames, times, distances):
            fh.write(f"{fr},{t/1000.0:.4f},{d:.4f}\n")

    if working_dir:
        try:
            append_analysis_summary(
                working_dir=working_dir,
                analysis_type="Ligand_Pocket_COM_Distance",
                statistics={
                    "n_frames": len(distances),
                    "cutoff_angstrom": cutoff,
                    "n_pocket_atoms": n_pocket_atoms,
                    "mean_distance_angstrom": mean_dist,
                    "std_distance_angstrom": std_dist,
                    "min_distance_angstrom": min_dist,
                    "max_distance_angstrom": max_dist,
                },
                files={"topology": topology_file, "trajectory": trajectory_file, "data": output_file},
                metadata={
                    "ligand_selection": ligand_selection,
                    "protein_selection": protein_selection,
                    "pocket_residues": pocket_resids,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to write analysis summary: {e}")

    return {
        "success": True,
        "n_pocket_atoms": n_pocket_atoms,
        "n_pocket_residues": len(pocket_resids),
        "mean_distance": mean_dist,
        "std_distance": std_dist,
        "min_distance": min_dist,
        "max_distance": max_dist,
        "n_frames": len(distances),
        "output_file": output_file,
        "message": f"Ligand-pocket COM distance: mean={mean_dist:.2f} Å",
    }


def compute_ligand_pocket_distance_from_universe(
    u,
    *,
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname LIG",
    protein_selection: str = "protein",
    cutoff: float = 5.0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
) -> Dict[str, Any]:
    """Ligand pocket distance from a pre-loaded Universe (single traverse)."""
    if not HAS_MDA or not HAS_NUMPY:
        return {"success": False, "error": "MDAnalysis and numpy are required"}

    u.trajectory[0]
    ligand = u.select_atoms(ligand_selection)
    if len(ligand) == 0:
        return {"success": False, "error": f"Ligand selection matched 0 atoms: '{ligand_selection}'"}

    pocket_sel_str = f"({protein_selection}) and around {cutoff} ({ligand_selection})"
    pocket_atoms = u.select_atoms(pocket_sel_str)
    if len(pocket_atoms) == 0:
        return {
            "success": False,
            "error": f"No protein atoms within {cutoff} Å of ligand at frame 0",
        }

    pocket_frozen = u.atoms[pocket_atoms.indices]
    pocket_resids = sorted(set(pocket_frozen.resids))

    frames, times, distances = [], [], []
    for ts in u.trajectory[::frame_interval]:
        # Trust already-wrapped trajectories; do not re-wrap pocket/ligand
        # residue-by-residue before COM (breaks large pocket COMs).
        dist = minimum_image_distance(
            pocket_frozen.center_of_mass(), ligand.center_of_mass(), getattr(ts, "dimensions", None)
        )
        frames.append(int(ts.frame))
        times.append(float(ts.time))
        distances.append(dist)

    cleaned, _, n_removed = clean_pbc_distance_series(distances)
    if n_removed:
        logger.info("Ligand-pocket distance: removed %d PBC spike(s)", n_removed)
        distances = [float(v) for v in cleaned]

    return finalize_ligand_pocket_distance_result(
        frames,
        times,
        distances,
        ligand_selection=ligand_selection,
        protein_selection=protein_selection,
        cutoff=cutoff,
        pocket_resids=pocket_resids,
        n_pocket_atoms=len(pocket_frozen),
        output_file=output_file,
        topology_file=topology_file,
        trajectory_file=trajectory_file,
        working_dir=working_dir,
    )


@tool
def calculate_com_distance(
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
    Calculate per-frame center-of-mass (COM) distance between two explicit atom selections.

    **Use when** the user wants the distance between the COM of group A and the COM
    of group B — e.g. whole protein vs ligand, N-terminal domain vs C-terminal domain,
    or chain A vs chain B. You choose both selections explicitly.

    **Do NOT use for** "ligand pocket distance" or "binding-site stability" — use
    ``calculate_ligand_pocket_distance`` instead, which identifies pocket atoms near
    the ligand at frame 0 and tracks ligand COM vs that pocket COM.

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr) - full path
        trajectory_file: Trajectory file (.xtc, .trr, .dcd) - full path
        selection1: First MDAnalysis selection (e.g. ``"protein"``, ``"resid 1:100"``)
        selection2: Second MDAnalysis selection (e.g. ``"resname ATP"``)
        label1: Plot label for selection 1 (default: ``"group1"``)
        label2: Plot label for selection 2 (default: ``"group2"``)
        output_file: CSV filename (default: ``"com_distance.csv"``; subset: ``com_distance_{qualifier}.csv``)
        working_dir: Directory for output files
        frame_interval: Process every Nth frame (default: 1)
        selection1_from_file: Optional nearby_residues JSON/CSV for selection1
        selection2_from_file: Optional nearby_residues JSON/CSV for selection2
        selection_key: JSON key to read (default mda_selection_heavy)

    Returns:
        Dict with COM distance statistics and output path.

    Standard outputs: ``com_distance.csv``, plot as ``com_distance.png``.
    """
    try:
        # Setup working directory
        original_dir = None
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)

        # Validate dependencies
        if not HAS_MDA or not HAS_NUMPY:
            return {
                "success": False,
                "error": "MDAnalysis and numpy are required for COM distance calculation",
            }

        # Validate input files
        if not os.path.exists(topology_file):
            return {"success": False, "error": f"Topology file not found: {topology_file}"}
        if not os.path.exists(trajectory_file):
            return {"success": False, "error": f"Trajectory file not found: {trajectory_file}"}

        logger.info(
            f"Calculating COM distance: '{selection1}' ({label1}) vs '{selection2}' ({label2})"
        )

        from .proximity_analyzer import apply_selection_from_files

        resolved = apply_selection_from_files(
            {
                "selection1": selection1,
                "selection2": selection2,
                "selection1_from_file": selection1_from_file,
                "selection2_from_file": selection2_from_file,
                "selection_key": selection_key,
            },
            working_dir=working_dir,
        )
        selection1 = resolved.get("selection1", selection1)
        selection2 = resolved.get("selection2", selection2)

        u = mda.Universe(topology_file, trajectory_file)
        result = compute_com_distance_from_universe(
            u,
            topology_file=topology_file,
            trajectory_file=trajectory_file,
            selection1=selection1,
            selection2=selection2,
            label1=label1,
            label2=label2,
            output_file=output_file,
            working_dir=working_dir,
            frame_interval=frame_interval,
        )
        if working_dir and original_dir:
            os.chdir(original_dir)
        return result

    except Exception as e:
        logger.exception(f"COM distance calculation failed: {e}")
        if working_dir and original_dir:
            os.chdir(original_dir)
        return {"success": False, "error": str(e)}


@tool
def calculate_ligand_pocket_distance(
    topology_file: str,
    trajectory_file: str,
    ligand_selection: str = "resname LIG",
    protein_selection: str = "protein",
    cutoff: float = 5.0,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    frame_interval: int = 1,
    pocket_selection: str = "",
    pocket_map_json: str = "",
    label: str = "",
    pocket_resids: Optional[list] = None,
    hpc_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Track ligand displacement from a **local** binding pocket (single sim).

    **Family / comparative MD:** prefer ``calculate_consensus_pocket_metrics``
    (uses pocket_mapped / reference-pocket residues and writes
    ``reference_pocket_metrics.json``). Local pocket definition defaults to a
    **5 Å** frame-0 shell — a different contract from the family 15 Å ∩
    global_mapped pocket used for transferable COM / axis-angle features.

    **Use when** the user asks for single-system ligand–pocket distance without
    requesting MSA-mapped / consensus pocket metrics.

    **Do NOT use for** family clustering feature tables, or for arbitrary
    two-group COM — use ``calculate_com_distance`` with explicit selections.

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr).
        trajectory_file: Trajectory file (.xtc, .trr, .dcd).
        ligand_selection: Ligand MDAnalysis selection (default: ``"resname LIG"``).
        protein_selection: Protein atoms for pocket search (default: ``"protein"``).
        cutoff: Å cutoff for frame-0 pocket when no mapped pocket is supplied (default 5.0).
        output_file: CSV filename (default: ``"ligand_pocket_distance.csv"``).
        working_dir: Output directory.
        frame_interval: Process every Nth frame (default: 1).
        pocket_selection: Explicit MDAnalysis protein selection for the pocket.
        pocket_map_json: Shared ``pocket_mapped.json`` from pre-combined mapping.
        label: Simulation label used to look up ``pocket_map_json``.
        pocket_resids: Residue numbers to use as the pocket (alternative to JSON).
        hpc_dir: Optional HPC slot used when trajectory paths are relative.

    Returns:
        Dict with pocket atom count, distance statistics, and output path.
    """
    try:
        original_dir = None
        if working_dir:
            os.makedirs(working_dir, exist_ok=True)
            original_dir = os.getcwd()
            os.chdir(working_dir)

        if not HAS_MDA or not HAS_NUMPY:
            return {
                "success": False,
                "error": "MDAnalysis and numpy are required for ligand pocket distance calculation",
            }

        from src.analysis.traj_resolve import resolve_topology_trajectory

        top, traj = resolve_topology_trajectory(
            topology_file,
            trajectory_file,
            hpc_dir=hpc_dir,
        )
        topology_file = top or topology_file
        trajectory_file = traj or trajectory_file

        if not os.path.exists(topology_file):
            return {"success": False, "error": f"Topology file not found: {topology_file}"}
        if not os.path.exists(trajectory_file):
            return {"success": False, "error": f"Trajectory file not found: {trajectory_file}"}

        pocket_source = "local_cutoff"
        pocket_sel_str = ""
        if pocket_map_json and label:
            try:
                from src.analysis.cross_sim_artifacts import pocket_selection_for_label

                payload = json.loads(Path(pocket_map_json).read_text(encoding="utf-8"))
                mapped = pocket_selection_for_label(payload, label)
                if mapped:
                    pocket_sel_str = mapped
                    pocket_source = "pocket_mapped"
            except Exception as exc:
                logger.warning("pocket_mapped lookup failed: %s", exc)
        if not pocket_sel_str and pocket_selection:
            pocket_sel_str = str(pocket_selection)
            pocket_source = "pocket_selection"
        if not pocket_sel_str and pocket_resids:
            nums = [str(int(r)) for r in pocket_resids if r is not None]
            if nums:
                pocket_sel_str = f"({protein_selection}) and resid " + " ".join(nums)
                pocket_source = "pocket_resids"

        logger.info(
            "Ligand pocket distance: ligand=%r pocket_source=%s cutoff=%s Å",
            ligand_selection,
            pocket_source,
            cutoff,
        )

        u = mda.Universe(topology_file, trajectory_file)

        # ── Step 1: identify pocket atoms ────────────────────────────────
        u.trajectory[0]
        ligand = u.select_atoms(ligand_selection)
        if len(ligand) == 0:
            return {
                "success": False,
                "error": f"Ligand selection matched 0 atoms: '{ligand_selection}'",
            }

        protein = u.select_atoms(protein_selection)
        if len(protein) == 0:
            return {
                "success": False,
                "error": f"Protein selection matched 0 atoms: '{protein_selection}'",
            }

        if not pocket_sel_str:
            pocket_sel_str = (
                f"({protein_selection}) and around {cutoff} ({ligand_selection})"
            )
            pocket_source = "local_cutoff"
        pocket_atoms = u.select_atoms(pocket_sel_str)

        if len(pocket_atoms) == 0:
            return {
                "success": False,
                "error": (
                    f"No protein atoms found within {cutoff} Å of ligand at frame 0.  "
                    f"Try increasing the cutoff or checking residue names."
                ),
            }

        # Freeze the pocket atom indices so the selection does not change across frames
        pocket_indices = pocket_atoms.indices
        pocket_frozen = u.atoms[pocket_indices]

        # Build a human-readable description of pocket residues
        pocket_resids = sorted(set(pocket_frozen.resids))
        pocket_resnames = sorted(set(pocket_frozen.resnames))
        pocket_desc = (
            f"{len(pocket_frozen)} atoms | residues {pocket_resids[:6]}"
            + ("..." if len(pocket_resids) > 6 else "")
        )
        logger.info(f"Pocket atoms (frame 0, cutoff {cutoff} Å): {pocket_desc}")
        logger.info(f"Pocket residue names: {pocket_resnames}")

        # ── Step 2: per-frame COM-to-COM distance ─────────────────────────
        frames, times, distances = [], [], []

        for ts in u.trajectory[::frame_interval]:
            # Trust already-wrapped trajectories; do not re-wrap pocket/ligand
            # residue-by-residue before COM (breaks large pocket COMs).
            com_pocket = pocket_frozen.center_of_mass()
            com_ligand = ligand.center_of_mass()
            dist = minimum_image_distance(
                com_pocket, com_ligand, getattr(ts, "dimensions", None)
            )
            frames.append(int(ts.frame))
            times.append(float(ts.time) / 1000.0)  # ps → ns
            distances.append(dist)

        # Strip residual transient PBC spikes before stats + CSV output.
        cleaned, _, n_spikes = clean_pbc_distance_series(distances)
        if n_spikes:
            logger.info(
                "Ligand pocket distance: removed %d transient PBC spike(s)", n_spikes
            )
            distances = [float(v) for v in cleaned]

        distances_arr = np.array(distances)
        mean_dist = float(np.mean(distances_arr))
        std_dist = float(np.std(distances_arr))
        min_dist = float(np.min(distances_arr))
        max_dist = float(np.max(distances_arr))

        # ── Write CSV ─────────────────────────────────────────────────────
        if not output_file:
            lig_tag = ligand_selection.replace(" ", "_")
            output_file = f"ligand_pocket_distance_{lig_tag}_cutoff{int(cutoff)}A.csv"

        with open(output_file, "w") as fh:
            fh.write("frame,time_ns,distance_angstrom\n")
            for fr, t, d in zip(frames, times, distances):
                fh.write(f"{fr},{t:.4f},{d:.4f}\n")

        logger.info(f"Ligand pocket distance data saved to {output_file}")

        # ── Analysis summary ──────────────────────────────────────────────
        if working_dir:
            try:
                append_analysis_summary(
                    working_dir=working_dir,
                    analysis_type="Ligand_Pocket_COM_Distance",
                    statistics={
                        "n_frames": len(distances),
                        "cutoff_angstrom": cutoff,
                        "n_pocket_atoms": len(pocket_frozen),
                        "n_pocket_residues": len(pocket_resids),
                        "mean_distance_angstrom": mean_dist,
                        "std_distance_angstrom": std_dist,
                        "min_distance_angstrom": min_dist,
                        "max_distance_angstrom": max_dist,
                    },
                    files={
                        "topology": topology_file,
                        "trajectory": trajectory_file,
                        "data": output_file,
                    },
                    metadata={
                        "ligand_selection": ligand_selection,
                        "protein_selection": protein_selection,
                        "cutoff_angstrom": cutoff,
                        "pocket_residues": pocket_resids,
                        "pocket_resnames": pocket_resnames,
                        "pocket_description": pocket_desc,
                    },
                )
            except Exception as e:
                logger.warning(f"Failed to write analysis summary: {e}")

            os.chdir(original_dir)

        return {
            "success": True,
            "n_pocket_atoms": len(pocket_frozen),
            "n_pocket_residues": len(pocket_resids),
            "pocket_residues": pocket_resids,
            "pocket_resnames": pocket_resnames,
            "pocket_selection": pocket_sel_str,
            "pocket_source": pocket_source,
            "topology_file": topology_file,
            "trajectory_file": trajectory_file,
            "cutoff_angstrom": cutoff,
            "mean_distance": mean_dist,
            "std_distance": std_dist,
            "min_distance": min_dist,
            "max_distance": max_dist,
            "n_frames": len(distances),
            "ligand_selection": ligand_selection,
            "output_file": output_file,
            "message": (
                f"Ligand-pocket COM distance (cutoff={cutoff} Å): "
                f"{len(pocket_frozen)} pocket atoms across {len(pocket_resids)} residues | "
                f"mean={mean_dist:.2f} Å, std={std_dist:.2f} Å, "
                f"min={min_dist:.2f} Å, max={max_dist:.2f} Å over {len(distances)} frames"
            ),
        }

    except Exception as e:
        logger.exception(f"Ligand pocket distance calculation failed: {e}")
        if working_dir and original_dir:
            try:
                os.chdir(original_dir)
            except Exception:
                pass
        return {"success": False, "error": str(e)}
