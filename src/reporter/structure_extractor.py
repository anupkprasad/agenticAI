"""Extract frames from MD trajectories as PDB for visualization."""
import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def extract_first_frame_pdb(
    working_dir: str,
    hpc_subdir: str = "hpc",
    output_filename: str = "system_frame0.pdb",
) -> Optional[str]:
    """
    Extract the first frame from available topology/trajectory files as PDB.

    Selects protein, ligands, and coordinated ions (excluding bulk
    Na/Cl/K counter-ions and water) to keep the file lightweight for
    embedding in an HTML viewer.

    Search order for topology: md.gro, processed.gro, md.tpr, \\*.gro
    Trajectory (optional):     md.xtc, \\*.xtc

    Args:
        working_dir:     Base working directory (e.g. ``working_dir``).
        hpc_subdir:      Sub-folder inside *working_dir* that holds simulation
                         output (default ``"hpc"``).
        output_filename: Name of the PDB file to write inside *working_dir/reporter/*.

    Returns:
        Absolute path to the written PDB file, or ``None`` on failure.
    """
    try:
        import MDAnalysis as mda
    except ImportError:
        logger.warning("MDAnalysis not available – cannot extract PDB frame")
        return None

    hpc_dir = Path(working_dir) / hpc_subdir
    if not hpc_dir.is_dir():
        logger.warning(f"HPC directory not found: {hpc_dir}")
        return None

    # --- locate topology ------------------------------------------------
    topology: Optional[Path] = None
    for candidate in ("md.gro", "processed.gro", "md.tpr"):
        p = hpc_dir / candidate
        if p.exists():
            topology = p
            break
    if topology is None:
        gro_files = sorted(hpc_dir.glob("*.gro"))
        if gro_files:
            topology = gro_files[0]
    if topology is None:
        logger.warning("No topology file (.gro/.tpr) found in %s", hpc_dir)
        return None

    # --- locate trajectory (optional) -----------------------------------
    trajectory: Optional[Path] = None
    for candidate in ("md.xtc", "md.trr"):
        p = hpc_dir / candidate
        if p.exists():
            trajectory = p
            break
    if trajectory is None:
        xtc_files = sorted(hpc_dir.glob("*.xtc"))
        if xtc_files:
            trajectory = xtc_files[0]

    # --- load & write first frame ---------------------------------------
    try:
        if trajectory:
            u = mda.Universe(str(topology), str(trajectory))
        else:
            u = mda.Universe(str(topology))

        # Go to first frame
        u.trajectory[0]

        # Select protein + ligand + non-bulk ions (exclude water & Na/Cl/K counter-ions)
        # This keeps the PDB lightweight for HTML embedding
        _BULK_IONS = "resname NA NA+ CL CL- K K+ SOD CLA"
        _WATER     = "resname HOH WAT SOL TIP3 TIP4 SPC"

        sel_parts = []
        # Always include protein if present
        if len(u.select_atoms("protein")) > 0:
            sel_parts.append("protein")
        # Include nucleic acids if present
        if len(u.select_atoms("nucleic")) > 0:
            sel_parts.append("nucleic")
        # Include everything that is NOT protein, nucleic, water, or bulk ions (= ligands, cofactors, metals)
        other_sel = f"not protein and not nucleic and not ({_WATER}) and not ({_BULK_IONS})"
        if len(u.select_atoms(other_sel)) > 0:
            sel_parts.append(f"({other_sel})")

        if not sel_parts:
            # Fallback: just take everything minus water
            selection_str = f"not ({_WATER})"
        else:
            selection_str = " or ".join(sel_parts)

        selected = u.select_atoms(selection_str)

        reporter_dir = Path(working_dir) / "reporter"
        reporter_dir.mkdir(parents=True, exist_ok=True)
        output_path = reporter_dir / output_filename

        selected.write(str(output_path))

        logger.info(
            "Extracted first frame (%d atoms from %d total) → %s",
            len(selected), len(u.atoms), output_path,
        )
        return str(output_path)

    except Exception as exc:
        logger.error("Failed to extract PDB frame: %s", exc, exc_info=True)
        return None


def read_pdb_data(pdb_path: str) -> Optional[str]:
    """Read a PDB file and return its text content for embedding."""
    try:
        with open(pdb_path, "r") as f:
            return f.read()
    except Exception as exc:
        logger.error("Failed to read PDB file %s: %s", pdb_path, exc)
        return None
