"""MD Simulation State Definition for LangGraph"""
from typing import TypedDict, Optional, Dict, Any, List


# ── Agent I/O Directory Mapping ──────────────────────────────────────────────
# Each agent has a fixed input directory and output directory relative to
# working_dir/.  Agents decide only *file names*; the framework resolves
# full paths using this mapping.
#
#   input_dir = None  → agent reads user-supplied files (e.g. raw PDB)
#   input_dir = "hpc" → agent reads from working_dir/hpc/
#
AGENT_IO_MAP: Dict[str, Dict[str, Optional[str]]] = {
    "preprocess": {"input_dir": None,          "output_dir": "preprocess"},
    "simsetup":   {"input_dir": "preprocess",  "output_dir": "simsetup"},
    "hpc":        {"input_dir": "simsetup",    "output_dir": "hpc"},
    "analysis":   {"input_dir": "hpc",         "output_dir": "analysis"},
    "reporter":   {"input_dir": "analysis",    "output_dir": "reporter"},
}


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
    subtask_type: Optional[str]    # "analysis_only", "setup_only", "preprocess_only", "reporter_only", "multi_agent", None
    subtask_type_initialized: Optional[bool]  # Whether subtask type has been initialized
    agent_list: Optional[List[str]]           # Ordered list of agents for multi-agent workflow
    required_inputs: Optional[Dict[str, bool]]  # What inputs this task requires
    input_validated: Optional[bool]             # Whether unified input validation has completed
    analysis_directory: Optional[str]   # Path to analysis output directory
    trajectory_paths: Optional[Dict[str, Optional[str]]]  # Trajectory, topology, energy paths for analysis-only
    
    # System info (extracted during input validation)
    system_info: Optional[Dict[str, Any]]   # Molecular system metadata: components, atom counts, frames, etc.

    # PDB Analysis (from supervisor validation)
    pdb_analysis: Optional[Dict[str, Any]]  # Output from PDB analyzer
    component_selection: Optional[Dict[str, Any]]  # User-specified component selection
    structured_prompt: Optional[str]  # High-level structured prompt for planner
    
    # Preprocessing stage
    raw_pdb: Optional[str]
    cleaned_pdb: Optional[str]
    preprocessing_report: Optional[str]
    preprocessing_issues: List[str]
    
    # Ligand / ion component tracking (set by preprocessing, consumed by setup)
    ligand_files: Optional[List[str]]          # Paths to separated ligand PDB files
    ligand_resnames: Optional[List[str]]       # Residue names (e.g. ["ATP", "GTP"])
    ion_files: Optional[List[str]]             # Paths to separated ion PDB files
    ion_resnames: Optional[List[str]]          # Residue names (e.g. ["MG", "ZN"])
    
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

    # Reporter stage
    reporter_output: Optional[Dict[str, Any]]  # Output from reporter agent
    report_type: Optional[str]                 # "comprehensive", "executive", "custom"
    include_literature: Optional[bool]         # Whether to search PubMed
    literature_keywords: Optional[List[str]]   # Manual PubMed keywords
    reporter_plan: Optional[Dict[str, Any]]    # Reporter plan from supervisor
    reporter_instructions: Optional[str]       # Reporter-specific instructions from planner
    
    # Control flow & Execution tracking
    current_node: Optional[str]        # Track which node we're currently in
    next_node: Optional[str]
    human_feedback: Optional[str]
    working_directory: Optional[str]   # Root working directory (e.g., ./working_dir)
    
    # Enriched / rephrased prompt (set once after input validation)
    enriched_prompt: Optional[str]     # Unified enriched goal used by planner and agents

    # Agent-specific output directories (hardcoded structure)
    preprocess_dir: Optional[str]      # working_dir/preprocess/
    simsetup_dir: Optional[str]        # working_dir/simsetup/
    hpc_dir: Optional[str]             # working_dir/hpc/
    analysis_dir: Optional[str]        # working_dir/analysis/
    
    execution_path: List[str]          # Track which nodes have been visited
    execution_plan: Optional[Dict[str, Any]]  # Detailed execution plan from planner
    plan_executed: bool                # Whether execution plan has been created
    rephrased_goal: Optional[str]      # LLM-rephrased user goal

    # Agent-specific instruction sections (extracted from full execution plan)
    preprocessing_instructions: Optional[str]
    setup_instructions: Optional[str]
    hpc_instructions: Optional[str]
    analysis_instructions: Optional[str]

    # Agent retry counters (used by _assign_field_agent_tasks)
    current_agent_idx: Optional[int]
    preprocess_retry_count: Optional[int]
    setup_retry_count: Optional[int]
    hpc_retry_count: Optional[int]
    analysis_retry_count: Optional[int]
    reporter_retry_count: Optional[int]

    # Intermediate validation artifacts
    pdb_summary: Optional[str]              # Human-readable PDB summary (for enrichment)
    file_info: Optional[Dict[str, Any]]     # Trajectory/topology file info (analysis tasks)
    reporter_file_info: Optional[Dict[str, Any]]  # Analysis output file info (reporter tasks)

    # Final report
    final_report: Optional[str]        # LLM-generated or fallback workflow completion report
    workflow_status: Optional[str]     # "completed", "failed"
    
    # Error & Warning tracking
    errors: List[str]                  # List of errors encountered during workflow
    warnings: List[str]                # List of warnings generated during workflow

    # ── Multi-Simulation Mode ─────────────────────────────────────────────
    is_multi_simulation: Optional[bool]          # True when running multiple PDBs
    multi_sim_phase: Optional[str]               # "planning" | "executing_sims" | "combined_analysis" | "combined_reporter" | None
    pdb_list: Optional[List[str]]                # Original PDB file paths from CLI / goal extraction
    sim_prompts: Optional[List[Dict[str, Any]]]  # Per-sim prompts from master planner [{prompt, pdb, label, working_dir}, ...]
    combined_analysis_plan: Optional[str]        # LLM plan text for cross-simulation analysis
    current_sim_index: Optional[int]             # Index into sim_prompts (which sim is next)
    completed_sim_states: Optional[List[Dict[str, Any]]]  # Saved state snapshots after each sim completes
    sim_working_dirs: Optional[List[str]]        # Per-sim working directories (e.g., base_dir/1abc/)
