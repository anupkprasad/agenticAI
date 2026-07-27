"""
Task Type Detector for Workflow Routing

Determines required inputs based on subtask type.
"""
from typing import Optional, Dict, List


# Which CLI agent names require a PDB file / trajectory
_PDB_AGENTS = {"preprocess", "simsetup", "hpcjob"}
_TRAJ_AGENTS = {"analysis"}


def detect_task_required_inputs(
    subtask_type: Optional[str],
    agent_list: Optional[List[str]] = None
) -> Dict[str, bool]:
    """
    Determine which inputs are required based on subtask type.

    Args:
        subtask_type: Type of subtask (analysis_only, setup_only, preprocess_only,
                      hpc_only, reporter_only, multi_agent, full_task)
        agent_list: Ordered list of agent names for multi_agent workflows

    Returns:
        Dict mapping input requirements to boolean flags
    """
    inputs_needed = {
        "pdb_required": True,
        "pdb_analysis_required": True,
        "trajectory_path_required": False,
        "topology_required": False
    }

    if subtask_type == "analysis_only":
        inputs_needed.update({
            "pdb_required": False,
            "pdb_analysis_required": False,
            "trajectory_path_required": True,
            "topology_required": True
        })
    elif subtask_type == "reporter_only":
        inputs_needed.update({
            "pdb_required": False,
            "pdb_analysis_required": False,
            "trajectory_path_required": False,
            "topology_required": False
        })
    elif subtask_type == "hpc_only":
        # Existing HPC dirs / continuation: no fresh PDB analysis required.
        inputs_needed.update({
            "pdb_required": False,
            "pdb_analysis_required": False,
            "trajectory_path_required": False,
            "topology_required": False,
        })
    elif subtask_type in ["setup_only", "preprocess_only"]:
        inputs_needed.update({
            "pdb_required": True,
            "pdb_analysis_required": True
        })
    elif subtask_type == "multi_agent":
        # Derive requirements from the union of involved agents
        agents = set(agent_list or [])
        pdb_needed = bool(agents & _PDB_AGENTS)               # any PDB agent present
        traj_needed = bool(agents & _TRAJ_AGENTS) and not pdb_needed  # analysis w/o PDB
        reporter_only = agents.issubset({"reporter"})           # reporter alone
        inputs_needed.update({
            "pdb_required": pdb_needed,
            "pdb_analysis_required": pdb_needed,
            "trajectory_path_required": traj_needed,
            "topology_required": traj_needed,
        })

    return inputs_needed
