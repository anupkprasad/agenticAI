"""
Task Type Detector for Workflow Routing

Determines required inputs based on subtask type.
"""
from typing import Optional, Dict


def detect_task_required_inputs(subtask_type: Optional[str]) -> Dict[str, bool]:
    """
    Determine which inputs are required based on subtask type.
    
    Args:
        subtask_type: Type of subtask (analysis_only, setup_only, preprocess_only, full_task)
        
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
    elif subtask_type in ["setup_only", "preprocess_only"]:
        inputs_needed.update({
            "pdb_required": True,
            "pdb_analysis_required": True
        })
    
    return inputs_needed
