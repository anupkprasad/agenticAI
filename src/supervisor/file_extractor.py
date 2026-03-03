"""
File Name Extractor for Analysis Tasks

Extracts and validates file paths from user goals and directories.
"""
import os
import re
from typing import Optional, Tuple


def extract_file_names_from_goal(
    user_goal: str, hpc_dir: str
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Extract explicit file names from user goal for analysis tasks.
    
    Priority:
    1. Use explicitly stated file names from user goal
    2. Default to md.* pattern (md.gro, md.xtc, md.edr)
    3. Return None to trigger auto-discovery
    
    Args:
        user_goal: User's analysis goal
        hpc_dir: HPC output directory path
        
    Returns:
        Tuple of (topology_file, trajectory_file, energy_file) or None values
    """
    topology_file = None
    trajectory_file = None
    energy_file = None
    
    # Pattern to match explicit file names in user goal
    goal_lower = user_goal.lower()
    
    # Look for topology files (.gro, .pdb, .tpr)
    topo_pattern = r'([\w\-]+\.(?:gro|pdb|tpr))'
    topo_matches = re.findall(topo_pattern, goal_lower)
    if topo_matches:
        candidate = topo_matches[0]
        candidate_path = os.path.join(hpc_dir, candidate)
        if os.path.exists(candidate_path):
            topology_file = candidate_path
    
    # Look for trajectory files (.xtc, .trr)
    traj_pattern = r'([\w\-]+\.(?:xtc|trr))'
    traj_matches = re.findall(traj_pattern, goal_lower)
    if traj_matches:
        candidate = traj_matches[0]
        candidate_path = os.path.join(hpc_dir, candidate)
        if os.path.exists(candidate_path):
            trajectory_file = candidate_path
    
    # Look for energy files (.edr)
    energy_pattern = r'([\w\-]+\.edr)'
    energy_matches = re.findall(energy_pattern, goal_lower)
    if energy_matches:
        candidate = energy_matches[0]
        candidate_path = os.path.join(hpc_dir, candidate)
        if os.path.exists(candidate_path):
            energy_file = candidate_path
    
    # If no explicit files found in goal, default to md.* pattern
    if not topology_file:
        md_gro = os.path.join(hpc_dir, "md.gro")
        md_pdb = os.path.join(hpc_dir, "md.pdb")
        md_tpr = os.path.join(hpc_dir, "md.tpr")
        if os.path.exists(md_gro):
            topology_file = md_gro
        elif os.path.exists(md_pdb):
            topology_file = md_pdb
        elif os.path.exists(md_tpr):
            topology_file = md_tpr
    
    if not trajectory_file:
        md_xtc = os.path.join(hpc_dir, "md.xtc")
        md_trr = os.path.join(hpc_dir, "md.trr")
        if os.path.exists(md_xtc):
            trajectory_file = md_xtc
        elif os.path.exists(md_trr):
            trajectory_file = md_trr
    
    if not energy_file:
        md_edr = os.path.join(hpc_dir, "md.edr")
        if os.path.exists(md_edr):
            energy_file = md_edr
    
    return topology_file, trajectory_file, energy_file
