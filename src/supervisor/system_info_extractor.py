"""
System Info Extractor

Extracts molecular system metadata from PDB/GRO files (preprocess/setup tasks)
or from topology + trajectory files (analysis tasks) using MDAnalysis.
"""
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def extract_system_info_from_structure(structure_file: str) -> Dict[str, Any]:
    """Extract system info from a single structure file (PDB or GRO).
    
    Used for preprocess/simsetup tasks where only the input structure exists.
    
    Args:
        structure_file: Path to .pdb or .gro file
        
    Returns:
        Dict with system composition and metadata
    """
    if not os.path.exists(structure_file):
        return {"success": False, "error": f"File not found: {structure_file}"}

    try:
        import MDAnalysis as mda
    except ImportError:
        return {"success": False, "error": "MDAnalysis not installed"}

    try:
        u = mda.Universe(structure_file)
        return _extract_from_universe(u, has_trajectory=False)
    except Exception as e:
        return {"success": False, "error": f"Failed to load {structure_file}: {e}"}


def extract_system_info_from_trajectory(
    topology_file: str,
    trajectory_file: str
) -> Dict[str, Any]:
    """Extract system info from topology + trajectory files.
    
    Used for analysis tasks where simulation output exists.
    Loads both files in MDAnalysis to get composition AND trajectory metadata.
    
    Args:
        topology_file: Path to .gro, .pdb, or .tpr file
        trajectory_file: Path to .xtc or .trr file
        
    Returns:
        Dict with system composition, trajectory metadata, and component details
    """
    if not os.path.exists(topology_file):
        return {"success": False, "error": f"Topology file not found: {topology_file}"}
    if not os.path.exists(trajectory_file):
        return {"success": False, "error": f"Trajectory file not found: {trajectory_file}"}

    try:
        import MDAnalysis as mda
    except ImportError:
        return {"success": False, "error": "MDAnalysis not installed"}

    try:
        u = mda.Universe(topology_file, trajectory_file)
        return _extract_from_universe(u, has_trajectory=True)
    except Exception as e:
        return {"success": False, "error": f"Failed to load trajectory: {e}"}


def _extract_from_universe(u, has_trajectory: bool = False) -> Dict[str, Any]:
    """Core extraction logic from an MDAnalysis Universe.
    
    Args:
        u: MDAnalysis Universe object
        has_trajectory: Whether a trajectory is loaded (enables frame info)
        
    Returns:
        Dict with system_info fields
    """
    info: Dict[str, Any] = {"success": True}

    # ---- Basic counts ----
    info["total_atoms"] = len(u.atoms)
    info["total_residues"] = len(u.residues)

    # ---- Components ----
    components: Dict[str, Any] = {}

    # Protein
    protein = u.select_atoms("protein")
    if len(protein) > 0:
        chain_ids = sorted(set(protein.chainIDs)) if hasattr(protein, "chainIDs") else []
        components["protein"] = {
            "present": True,
            "atom_count": len(protein),
            "residue_count": len(protein.residues),
            "chains": chain_ids,
        }
    else:
        components["protein"] = {"present": False, "atom_count": 0, "residue_count": 0}

    # Water
    water_sel = "resname HOH WAT TIP3 SOL"
    water = u.select_atoms(water_sel)
    components["water"] = {
        "present": len(water) > 0,
        "atom_count": len(water),
        "residue_count": len(water.residues) if len(water) > 0 else 0,
    }

    # Ions (common MD ions)
    ion_sel = "resname NA CL K CA MG ZN FE CU NA+ CL- SOD CLA"
    ions = u.select_atoms(ion_sel)
    if len(ions) > 0:
        ion_types = {}
        for rname in sorted(set(ions.residues.resnames)):
            ion_atoms = ions.select_atoms(f"resname {rname}")
            ion_types[rname] = len(ion_atoms.residues)
        components["ions"] = {
            "present": True,
            "atom_count": len(ions),
            "types": ion_types,
        }
    else:
        components["ions"] = {"present": False, "atom_count": 0, "types": {}}

    # Ligands (everything else)
    ligand = u.select_atoms(f"not protein and not ({water_sel}) and not ({ion_sel})")
    if len(ligand) > 0:
        lig_names = sorted(set(ligand.residues.resnames))
        components["ligand"] = {
            "present": True,
            "atom_count": len(ligand),
            "residue_names": lig_names,
        }
    else:
        components["ligand"] = {"present": False, "atom_count": 0, "residue_names": []}

    info["components"] = components

    # ---- Trajectory metadata (only when trajectory is loaded) ----
    if has_trajectory and hasattr(u.trajectory, "n_frames"):
        traj = u.trajectory
        info["trajectory"] = {
            "n_frames": traj.n_frames,
            "dt_ps": round(traj.dt, 2) if hasattr(traj, "dt") else None,
            "total_time_ps": round(traj.totaltime, 2) if hasattr(traj, "totaltime") else None,
            "total_time_ns": round(traj.totaltime / 1000.0, 3) if hasattr(traj, "totaltime") else None,
        }

    # ---- Human-readable summary line ----
    parts = []
    if components["protein"]["present"]:
        parts.append(f"protein ({components['protein']['residue_count']} residues)")
    if components["ligand"]["present"]:
        parts.append(f"ligand(s): {', '.join(components['ligand']['residue_names'])}")
    if components["ions"]["present"]:
        ion_str = ", ".join(f"{k}:{v}" for k, v in components["ions"]["types"].items())
        parts.append(f"ions ({ion_str})")
    if components["water"]["present"]:
        parts.append(f"water ({components['water']['residue_count']} molecules)")
    info["summary"] = f"{info['total_atoms']} atoms: " + ", ".join(parts) if parts else f"{info['total_atoms']} atoms"

    return info
