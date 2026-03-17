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
    
    # Subtask-specific workflow
    subtask_type: Optional[str]    # "analysis_only", "setup_only", "preprocess_only", None
    required_inputs: Optional[Dict[str, bool]]  # What inputs this task requires
    analysis_validated: Optional[bool]  # Whether analysis-only inputs have been validated
    trajectory_paths: Optional[Dict[str, Optional[str]]]  # Trajectory, topology, energy paths for analysis-only
    
    # PDB Analysis (from supervisor validation)
    pdb_analysis: Optional[Dict[str, Any]]  # Output from PDB analyzer
    component_selection: Optional[Dict[str, Any]]  # User-specified component selection
    structured_prompt: Optional[str]  # High-level structured prompt for planner
    
    # Preprocessing stage
    raw_pdb: Optional[str]
    cleaned_pdb: Optional[str]
    preprocessing_report: Optional[str]
    preprocessing_issues: List[str]
    
    # File registry - tracks all files created during workflow
    file_registry: Dict[str, Dict[str, str]]  # {file_path: {"type": "protein", "description": "...", "stage": "preprocess"}}
    
    # Generated files tracking by agent - centralized tracking of important outputs
    generated_files: Dict[str, Dict[str, Dict[str, str]]]  # {agent: {file_key: {"path": "...", "description": "..."}}}
    
    # Setup stage
    topology: Optional[str]
    coordinates: Optional[str]
    mdp_files: Dict[str, str]      # {"minim": "minim.mdp", "nvt": "nvt.mdp", ...}
    setup_report: Optional[str]
    setup_issues: List[str]
    
    # HPC stage
    hpc_action: Optional[str]
    hpc_output_directory: Optional[str]  # Path to HPC output directory (e.g., working_dir/hpc)
    job_script: Optional[str]
    job_id: Optional[str]
    job_status: Optional[str]
    trajectory_path: Optional[str]
    energy_file: Optional[str]  # Path to energy file (.edr)
    hpc_report: Optional[str]
    
    # Analysis stage
    analysis_action: Optional[str]
    analysis_request: Optional[str]
    analysis_results: Dict[str, Any]
    figures: List[str]
    conclusions: Optional[str]
    
    # Control flow & Execution tracking
    current_node: Optional[str]        # Track which node we're currently in
    next_node: Optional[str]
    human_feedback: Optional[str]
    working_directory: Optional[str]   # Root working directory (e.g., ./working_dir)
    
    # Agent-specific output directories (hardcoded structure)
    preprocess_dir: Optional[str]      # working_dir/preprocess/
    simsetup_dir: Optional[str]        # working_dir/simsetup/
    hpc_dir: Optional[str]             # working_dir/hpc/
    analysis_dir: Optional[str]        # working_dir/analysis/
    
    execution_path: List[str]          # Track which nodes have been visited
    execution_plan: Optional[Dict[str, Any]]  # Detailed execution plan from planner
    plan_executed: bool                # Whether execution plan has been created
    rephrased_goal: Optional[str]      # LLM-rephrased user goal
    
    # Error & Warning tracking
    errors: List[str]                  # List of errors encountered during workflow
    warnings: List[str]                # List of warnings generated during workflow
