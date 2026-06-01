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
import os
import logging
from typing import Dict, Any, Optional
from pathlib import Path
from langchain.tools import tool
from .summary_logger import append_analysis_summary

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
) -> Dict[str, Any]:
    """
    Calculate per-frame center-of-mass (COM) distance between two atom selections.

    Works for any pair of MDAnalysis selections: protein domains, protein-ligand,
    ligand-ions, chain-chain, etc.

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr) - full path
        trajectory_file: Trajectory file (.xtc, .trr, .dcd) - full path
        selection1: First MDAnalysis selection string (e.g. "protein", "resname ATP")
        selection2: Second MDAnalysis selection string (e.g. "resid 1:100 and name CA")
        label1: Human-readable label for selection 1 (e.g. "Protein", "N-terminal domain")
        label2: Human-readable label for selection 2 (e.g. "ATP", "C-terminal domain")
        output_file: Output CSV filename (default: "com_distance.csv") - saved in working_dir
        working_dir: Working directory for analysis (files will be written here)
        frame_interval: Process every Nth frame (default: 1 = every frame)

    Returns:
        Dict with COM distance results and statistics

    Output file format (CSV):
        frame,time_ns,distance_angstrom
        0,0.0000,12.3456
        1,0.1000,12.5678
        ...
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

        # Load universe
        u = mda.Universe(topology_file, trajectory_file)

        # Create atom groups
        group1 = u.select_atoms(selection1)
        group2 = u.select_atoms(selection2)

        if len(group1) == 0:
            return {"success": False, "error": f"Selection 1 matched 0 atoms: '{selection1}'"}
        if len(group2) == 0:
            return {"success": False, "error": f"Selection 2 matched 0 atoms: '{selection2}'"}

        logger.info(f"Selection 1 ({label1}): {len(group1)} atoms")
        logger.info(f"Selection 2 ({label2}): {len(group2)} atoms")

        # Compute per-frame COM distances
        frames = []
        times = []
        distances = []

        for ts in u.trajectory[::frame_interval]:
            com1 = group1.center_of_mass()
            com2 = group2.center_of_mass()
            dist = float(np.linalg.norm(com1 - com2))
            frames.append(ts.frame)
            times.append(ts.time / 1000.0)  # ps -> ns
            distances.append(dist)

        distances_arr = np.array(distances)

        # Statistics
        mean_dist = float(np.mean(distances_arr))
        std_dist = float(np.std(distances_arr))
        min_dist = float(np.min(distances_arr))
        max_dist = float(np.max(distances_arr))

        # Determine output file
        if not output_file:
            safe1 = label1.replace(" ", "_")
            safe2 = label2.replace(" ", "_")
            output_file = f"com_distance_{safe1}_vs_{safe2}.csv"

        # Write CSV
        with open(output_file, "w") as f:
            f.write("frame,time_ns,distance_angstrom\n")
            for fr, t, d in zip(frames, times, distances):
                f.write(f"{fr},{t:.4f},{d:.4f}\n")

        logger.info(f"COM distance data saved to {output_file}")

        # Determine analysis type label
        analysis_type = f"INTER_COM_Distance_{label1}_vs_{label2}"

        # Write to analysis summary
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
                    files={
                        "topology": topology_file,
                        "trajectory": trajectory_file,
                        "data": output_file,
                    },
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

            os.chdir(original_dir)

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
                f"mean={mean_dist:.2f} Å, std={std_dist:.2f} Å, "
                f"min={min_dist:.2f} Å, max={max_dist:.2f} Å"
            ),
        }

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
) -> Dict[str, Any]:
    """
    Track ligand displacement from its catalytic binding pocket over a trajectory.

    Step 1 — Identify pocket atoms: at the first trajectory frame, collect all
    protein atoms within ``cutoff`` Å of any ligand atom.  These atoms define
    the "catalytic pocket" reference group and stay fixed for the entire analysis.

    Step 2 — Track COM-to-COM distance: for every frame, compute the Euclidean
    distance between the center of mass (COM) of the pocket atoms and the COM of
    the ligand.  A rising distance indicates the ligand is moving away from the
    pocket; a stable, small distance indicates it remains bound.

    Args:
        topology_file: Topology file (.gro, .pdb, .tpr) — full path.
        trajectory_file: Trajectory file (.xtc, .trr, .dcd) — full path.
        ligand_selection: MDAnalysis selection for the ligand
            (default: ``"resname LIG"``).  Use the residue name from your
            topology, e.g. ``"resname ATP"`` or ``"resname INH"``.
        protein_selection: MDAnalysis selection for the protein atoms to search
            within (default: ``"protein"``).  Restrict to heavy atoms with
            ``"protein and not name H*"`` if desired.
        cutoff: Distance cutoff in Å used to identify pocket atoms at frame 0
            (default: 5.0).
        output_file: Output CSV filename (default: auto-generated from selections).
            Saved inside ``working_dir`` when provided.
        working_dir: Working directory for analysis output files.
        frame_interval: Process every Nth frame (default: 1 = every frame).

    Returns:
        Dict with keys:
            success (bool), n_pocket_atoms (int), pocket_selection (str),
            mean_distance / std_distance / min_distance / max_distance (float, Å),
            n_frames (int), output_file (str), message (str).

    Output CSV columns:
        frame, time_ns, distance_angstrom
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

        if not os.path.exists(topology_file):
            return {"success": False, "error": f"Topology file not found: {topology_file}"}
        if not os.path.exists(trajectory_file):
            return {"success": False, "error": f"Trajectory file not found: {trajectory_file}"}

        logger.info(
            f"Ligand pocket distance: ligand='{ligand_selection}', "
            f"protein='{protein_selection}', cutoff={cutoff} Å"
        )

        u = mda.Universe(topology_file, trajectory_file)

        # ── Step 1: identify pocket atoms at frame 0 ──────────────────────
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

        # MDAnalysis distance-based contact selection
        # Selects protein atoms within cutoff Å of any ligand atom at frame 0
        pocket_sel_str = (
            f"({protein_selection}) and around {cutoff} ({ligand_selection})"
        )
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
            com_pocket = pocket_frozen.center_of_mass()
            com_ligand = ligand.center_of_mass()
            dist = float(np.linalg.norm(com_pocket - com_ligand))
            frames.append(int(ts.frame))
            times.append(float(ts.time) / 1000.0)  # ps → ns
            distances.append(dist)

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
