"""MD Simulation State Definition for LangGraph"""
from typing import TypedDict, Optional, Dict, Any, List

class MDState(TypedDict):
    """Central state for MD simulation workflow."""
    
    # User input
    user_goal: str
    
    # Metadata & Configuration
    md_engine: str                 # "gromacs"
    force_field: str               # "amber99sb-ildn"
    water_model: str               # "tip3p"
    human_in_loop: bool
    
    # Preprocessing stage
    raw_pdb: Optional[str]
    cleaned_pdb: Optional[str]
    preprocessing_report: Optional[str]
    preprocessing_issues: List[str]
    
    # Setup stage
    topology: Optional[str]
    coordinates: Optional[str]
    mdp_files: Dict[str, str]      # {"minim": "minim.mdp", "nvt": "nvt.mdp", ...}
    setup_report: Optional[str]
    setup_issues: List[str]
    
    # HPC stage
    hpc_action: Optional[str]
    job_script: Optional[str]
    job_id: Optional[str]
    job_status: Optional[str]
    trajectory_path: Optional[str]
    hpc_report: Optional[str]
    
    # Analysis stage
    analysis_action: Optional[str]
    analysis_request: Optional[str]
    analysis_results: Dict[str, Any]
    figures: List[str]
    conclusions: Optional[str]
    
    # Control flow
    next_node: Optional[str]
    human_feedback: Optional[str]
    working_directory: Optional[str]
    
    # Error handling
    errors: List[str]
    warnings: List[str]
