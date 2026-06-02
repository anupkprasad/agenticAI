"""
Input Validator for Supervisor

Universal input validation for all task types (PDB-based and analysis-only).
"""
import os
import re
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


def validate_and_enrich_inputs(
    state: Dict[str, Any],
    subtask_type: str,
    llm_client,
    config: Dict[str, Any],
    analyze_pdb_tool,
    logger
) -> Dict[str, Any]:
    """
    Universal input validation and enrichment function for ALL task types.
    
    Args:
        state: Current MDState dictionary
        subtask_type: One of "analysis_only", "setup_only", "preprocess_only", "full_task"
        llm_client: LLM client instance
        config: Supervisor configuration
        analyze_pdb_tool: PDB analysis tool (for PDB-based tasks)
        logger: Logger instance
        
    Returns:
        Updated state dictionary with validation results and enriched prompt
    """
    # Import here to avoid circular dependencies
    from agentic.utils import log_agent_action
    
    logger.info("=" * 60)
    logger.info(f"INPUT_VALIDATION: Starting validation for task type: {subtask_type}")
    logger.info("=" * 60)
    
    user_goal = state.get("user_goal", "")
    working_directory = state.get("working_directory", ".")
    
    # TASK-SPECIFIC VALIDATION
    # PDB analysis only runs for tasks that need it (preprocess/setup/full).
    # Analysis-only and reporter-only skip PDB analysis entirely.
    if subtask_type == "analysis_only":
        state = _validate_analysis_files(state, user_goal, working_directory, logger)
    elif subtask_type == "reporter_only":
        state = _validate_reporter_files(state, user_goal, working_directory, logger)
    elif subtask_type == "multi_agent":
        state = _validate_multi_agent_inputs(state, user_goal, working_directory, analyze_pdb_tool, logger)
    else:
        # PDB-based tasks: analyze PDB then validate components
        state = _analyze_pdb_if_available(state, user_goal, working_directory, analyze_pdb_tool, logger)
        state = _validate_pdb_based_task(state, user_goal, working_directory, logger)
    
    # Mark unified validation complete
    state["input_validated"] = True
    state["next_node"] = "supervisor"
    
    logger.info("=" * 60)
    logger.info(f"INPUT_VALIDATION: Validation complete for {subtask_type}")
    logger.info("=" * 60)
    
    return state


def _analyze_pdb_if_available(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    analyze_pdb_tool,
    logger
) -> Dict[str, Any]:
    """Universal PDB structure analysis for ALL task types.
    
    Extracts PDB filename from user goal and analyzes structure if available.
    Stores comprehensive PDB analysis in state for all agents to use.
    
    For multi-simulation MASTER PLANNING (pdb_list present + not in per-sim phase),
    analyzes ALL PDbs for creating varied sim_prompts.
    
    For per-sim execution or single-sim mode, analyzes only the current PDB.
    
    If no PDB file is found, continues gracefully (state will have no pdb_analysis).
    """
    from agentic.utils import log_agent_action
    
    # Check if we're in multi-simulation MASTER PLANNING phase (not per-sim execution)
    # During per-sim execution, pdb_list is intentionally cleared from state so each
    # simulation only sees its own PDB via raw_pdb.
    pdb_list = state.get("pdb_list", [])
    multi_sim_phase = state.get("multi_sim_phase")
    is_multi_sim_master_planning = len(pdb_list) > 1 and multi_sim_phase != "executing_sims"
    
    if is_multi_sim_master_planning:
        # Multi-simulation MASTER PLANNING: analyze ALL PDbs in the list
        # This only happens once before per-sim loops start
        logger.info(f"INPUT_VALIDATION [MULTI-SIM MASTER]: Analyzing {len(pdb_list)} PDB files for planning")
        
        pdb_analyses = []
        for idx, pdb_path in enumerate(pdb_list):
            from pathlib import Path
            pdb_file = Path(pdb_path)
            
            # Validate file exists
            if not pdb_file.exists():
                logger.warning(f"INPUT_VALIDATION: PDB file not found: {pdb_path}")
                state["warnings"].append(f"PDB file not found: {pdb_path}")
                continue
            
            logger.info(f"INPUT_VALIDATION: Analyzing PDB {idx+1}/{len(pdb_list)}: {pdb_file.name}")
            
            pdb_analysis_result = analyze_pdb_tool.invoke({"pdb_file": str(pdb_file)})
            
            if not pdb_analysis_result.get("success"):
                logger.warning(f"INPUT_VALIDATION: PDB analysis failed for {pdb_file.name}")
                state["warnings"].append(f"PDB analysis failed: {pdb_file.name}")
                continue
            
            # Store analysis with PDB path reference
            analysis_data = pdb_analysis_result.get("analysis", {})
            analysis_data["pdb_file"] = str(pdb_file)
            analysis_data["pdb_name"] = pdb_file.name
            pdb_analyses.append(analysis_data)
            
            # Log detailed analysis for this PDB
            protein_sequences = {}
            if analysis_data.get("protein", {}).get("present"):
                chains_info = analysis_data.get("protein", {}).get("chains", {})
                for chain_id, chain_data in chains_info.items():
                    sequence = chain_data.get("sequence", "")
                    if sequence:
                        protein_sequences[chain_id] = sequence
            
            details = {
                "file": str(pdb_file),
                "total_atoms": analysis_data.get("total_atoms", 0),
                "total_residues": analysis_data.get("total_residues", 0),
                "components_available": analysis_data.get("components_available", {})
            }
            if protein_sequences:
                details["protein_sequences"] = protein_sequences
            
            log_agent_action(
                agent_name="supervisor.input_validation",
                action="PDB Structure Analysis",
                details=details
            )
        
        # Store all analyses in state
        if pdb_analyses:
            # Use first PDB for primary analysis (backward compatibility)
            state["pdb_analysis"] = pdb_analyses[0]
            state["raw_pdb"] = pdb_analyses[0]["pdb_file"]
            # Store all analyses for multi-sim planning
            state["all_pdb_analyses"] = pdb_analyses
            logger.info(
                f"INPUT_VALIDATION [MULTI-SIM MASTER]: Successfully analyzed "
                f"{len(pdb_analyses)} PDB files for planning"
            )
        else:
            logger.error("INPUT_VALIDATION [MULTI-SIM MASTER]: No PDbs could be analyzed")
            state["errors"].append("Failed to analyze any PDB files in multi-simulation mode")
        
        return state
    
    # Per-sim or single-simulation mode: extract and analyze only current PDB from goal or working_dir
    # In per-sim mode, the PDB has been copied to working_directory and raw_pdb points to it
    # Step 1: Extract PDB filename from user goal
    pdb_pattern = r'([\w\-]+\.pdb)'
    match = re.search(pdb_pattern, user_goal, re.IGNORECASE)
    
    if not match:
        logger.info("INPUT_VALIDATION: No PDB file mentioned in user goal - skipping PDB structure analysis")
        # Don't set error - this is OK for analysis_only tasks
        return state
    
    pdb_filename = match.group(1)
    pdb_path = os.path.join(working_directory, pdb_filename)
    state["raw_pdb"] = pdb_path
    
    # Check if we're in per-sim execution
    if multi_sim_phase == "executing_sims":
        logger.info(f"INPUT_VALIDATION [PER-SIM]: Analyzing current simulation PDB: {pdb_filename}")
    else:
        logger.info(f"INPUT_VALIDATION: Extracted PDB filename: {pdb_filename}")
    logger.info(f"INPUT_VALIDATION: Using working directory: {working_directory}")

    # Validate file exists
    if not os.path.exists(pdb_path):
        warning_msg = f"PDB file mentioned but not found: {pdb_path}"
        state["warnings"].append(warning_msg)
        logger.warning(f"INPUT_VALIDATION: {warning_msg}")
        return state

    # Step 2: Analyze PDB structure
    logger.info(f"INPUT_VALIDATION: Analyzing PDB structure: {pdb_path}")
    
    pdb_analysis_result = analyze_pdb_tool.invoke({"pdb_file": pdb_path})
    
    if not pdb_analysis_result.get("success"):
        error_msg = f"PDB analysis failed: {pdb_analysis_result.get('error', 'Unknown error')}"
        state["warnings"].append(error_msg)
        logger.warning(f"INPUT_VALIDATION: {error_msg}")
        logger.warning("INPUT_VALIDATION: Continuing with limited analysis, will use defaults")
        
        # Create minimal analysis for fallback
        state["pdb_analysis"] = {
            "total_atoms": 0,
            "total_residues": 0,
            "protein": {"present": True},
            "ligands": {"present": False},
            "water": {"present": False},
            "components_available": {},
            "chain_ids": []
        }
    else:
        # Store analysis in state
        state["pdb_analysis"] = pdb_analysis_result.get("analysis", {})
        logger.info(f"INPUT_VALIDATION: PDB analysis complete - {pdb_analysis_result.get('message', '')}")
        
        # Log detailed analysis
        analysis = state["pdb_analysis"]
        
        # Extract protein sequences if available
        protein_sequences = {}
        if analysis.get("protein", {}).get("present"):
            chains_info = analysis.get("protein", {}).get("chains", {})
            for chain_id, chain_data in chains_info.items():
                sequence = chain_data.get("sequence", "")
                if sequence:
                    protein_sequences[chain_id] = sequence
        
        # Build details dict
        details = {
            "file": pdb_path,
            "total_atoms": analysis.get("total_atoms", 0),
            "total_residues": analysis.get("total_residues", 0),
            "components_available": analysis.get("components_available", {})
        }
        
        # Add protein sequences if present
        if protein_sequences:
            details["protein_sequences"] = protein_sequences
        
        log_agent_action(
            agent_name="supervisor.input_validation",
            action="PDB Structure Analysis",
            details=details
        )
    
    return state


def _validate_pdb_based_task(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    logger
) -> Dict[str, Any]:
    """Validation for PDB-based tasks (setup/preprocess/full).
    
    Assumes PDB has already been analyzed by _analyze_pdb_if_available.
    Parses component selection and validates feasibility.
    """
    from agentic.utils import log_agent_action
    from .component_parser import parse_component_selection, validate_feasibility, build_human_summary
    
    analysis = state.get("pdb_analysis")
    if not analysis:
        state["errors"].append("PDB analysis not found - cannot proceed with setup/preprocessing")
        return state
    
    pdb_path = state.get("raw_pdb")

    # Extract system info from PDB/GRO file
    from .system_info_extractor import extract_system_info_from_structure
    sys_info = extract_system_info_from_structure(pdb_path)
    if sys_info.get("success"):
        state["system_info"] = sys_info
        logger.info(f"INPUT_VALIDATION: System info: {sys_info.get('summary', '')}")
    else:
        logger.warning(f"INPUT_VALIDATION: System info extraction failed: {sys_info.get('error')}")

    # Parse user intent for component selection
    component_selection = parse_component_selection(user_goal, analysis)
    state["component_selection"] = component_selection

    # Validate feasibility
    validation_result = validate_feasibility(user_goal, analysis, component_selection)
    
    if not validation_result["is_feasible"]:
        for error in validation_result["errors"]:
            state["errors"].append(error)
            logger.error(f"INPUT_VALIDATION: Feasibility error - {error}")
        return state
    
    for warning in validation_result["warnings"]:
        state["warnings"].append(warning)

    # Store PDB summary for enrichment
    state["pdb_summary"] = build_human_summary(analysis)
    
    pdb_validation_details = {
        "pdb_file": pdb_path,
        "component_selection": component_selection
    }
    sys_info = state.get("system_info")
    if sys_info and sys_info.get("success"):
        pdb_validation_details["system_summary"] = sys_info.get("summary", "")
        pdb_validation_details["total_atoms"] = sys_info.get("total_atoms", 0)
        pdb_validation_details["components"] = sys_info.get("components", {})

    log_agent_action(
        agent_name="supervisor.input_validation",
        action="PDB Input Validation Complete",
        details=pdb_validation_details
    )
    
    return state


def _validate_reporter_files(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    logger
) -> Dict[str, Any]:
    """Validate analysis summary files for reporter-only tasks."""
    from agentic.utils import log_agent_action
    
    analysis_output_dir = os.path.join(working_directory, "analysis")
    
    if not os.path.exists(analysis_output_dir):
        state["errors"].append(f"Analysis output directory not found: {analysis_output_dir}")
        return state
    
    logger.info(f"INPUT_VALIDATION: ✓ Analysis output directory found: {analysis_output_dir}")
    
    # Check for analysis_summary.jsonl
    summary_file = os.path.join(analysis_output_dir, "analysis_summary.jsonl")
    if not os.path.exists(summary_file):
        state["warnings"].append(f"Analysis summary file not found: {summary_file}")
        summary_file = None
    
    # Scan available analysis files
    available_files = []
    try:
        available_files = [f for f in os.listdir(analysis_output_dir)
                          if os.path.isfile(os.path.join(analysis_output_dir, f))]
        logger.info(f"INPUT_VALIDATION: Found {len(available_files)} analysis files")
    except Exception as e:
        state["warnings"].append(f"Failed to list files in {analysis_output_dir}: {e}")
    
    # Store validation results in proper state fields
    state["reporter_file_info"] = {
        "analysis_output_dir": analysis_output_dir,
        "analysis_summary_file": summary_file,
        "available_files": available_files,
        "total_files": len(available_files)
    }
    state["analysis_directory"] = analysis_output_dir
    
    log_agent_action(
        agent_name="supervisor.input_validation",
        action="Reporter Input Validation Complete",
        details={
            "analysis_directory": analysis_output_dir,
            "summary_file": summary_file,
            "total_files": len(available_files)
        }
    )
    
    return state


def _validate_analysis_files(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    logger
) -> Dict[str, Any]:
    """Validate trajectory/topology files for analysis-only tasks."""
    from agentic.utils import log_agent_action
    from .file_extractor import extract_file_names_from_goal
    
    hpc_output_dir = os.path.join(working_directory, "hpc")
    analysis_output_dir = os.path.join(working_directory, "analysis")
    
    if not os.path.exists(hpc_output_dir):
        state["errors"].append(f"HPC output directory not found: {hpc_output_dir}")
        return state
    
    logger.info(f"INPUT_VALIDATION: ✓ HPC output directory found: {hpc_output_dir}")
    
    # Discover files: explicit from goal → default md.* → auto-discover
    topology_file, trajectory_file, energy_file = extract_file_names_from_goal(
        user_goal, hpc_output_dir
    )
    
    # Auto-discover missing files by extension
    if not topology_file or not trajectory_file:
        try:
            hpc_files = os.listdir(hpc_output_dir)
            
            if not topology_file:
                for ext in [".gro", ".pdb", ".tpr"]:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        topology_file = os.path.join(hpc_output_dir, matching[0])
                        break
            
            if not trajectory_file:
                for ext in [".xtc", ".trr"]:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        trajectory_file = os.path.join(hpc_output_dir, matching[0])
                        break
            
            if not energy_file:
                for ext in [".edr"]:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        energy_file = os.path.join(hpc_output_dir, matching[0])
                        break
                    
        except Exception as e:
            state["errors"].append(f"Failed to list files in {hpc_output_dir}: {e}")
            return state
    
    # Store file_info
    file_info = {
        "hpc_output_dir": hpc_output_dir,
        "analysis_output_dir": analysis_output_dir,
        "topology_file": topology_file,
        "trajectory_file": trajectory_file,
        "energy_file": energy_file
    }
    
    if not topology_file:
        state["warnings"].append(f"No topology file (.gro, .pdb, .tpr) found in {hpc_output_dir}")
    if not trajectory_file:
        state["warnings"].append(f"No trajectory file (.xtc, .trr) found in {hpc_output_dir}")
    
    state["file_info"] = file_info
    
    # Set top-level state fields that analysis agent expects
    state["topology"] = topology_file
    state["trajectory_path"] = trajectory_file
    state["energy_file"] = energy_file
    state["hpc_output_directory"] = hpc_output_dir
    
    # Extract system info from topology + trajectory using MDAnalysis
    if topology_file and trajectory_file:
        from .system_info_extractor import extract_system_info_from_trajectory
        sys_info = extract_system_info_from_trajectory(topology_file, trajectory_file)
        if sys_info.get("success"):
            state["system_info"] = sys_info
            logger.info(f"INPUT_VALIDATION: System info: {sys_info.get('summary', '')}")
            if sys_info.get("trajectory"):
                traj = sys_info["trajectory"]
                logger.info(f"INPUT_VALIDATION: Trajectory: {traj.get('n_frames')} frames, {traj.get('total_time_ns')} ns")
        else:
            logger.warning(f"INPUT_VALIDATION: System info extraction failed: {sys_info.get('error')}")
    
    # Create analysis output directory if it doesn't exist
    os.makedirs(analysis_output_dir, exist_ok=True)
    
    # Build log details including system info if available
    validation_details = {
        "topology_file": topology_file,
        "trajectory_file": trajectory_file,
        "energy_file": energy_file,
        "hpc_output_directory": hpc_output_dir
    }
    sys_info = state.get("system_info")
    if sys_info and sys_info.get("success"):
        validation_details["system_summary"] = sys_info.get("summary", "")
        validation_details["total_atoms"] = sys_info.get("total_atoms", 0)
        validation_details["components"] = sys_info.get("components", {})
        if sys_info.get("trajectory"):
            traj = sys_info["trajectory"]
            validation_details["n_frames"] = traj.get("n_frames", 0)
            validation_details["total_time_ns"] = traj.get("total_time_ns", 0)

    log_agent_action(
        agent_name="supervisor.input_validation",
        action="Analysis Input Validation Complete",
        details=validation_details
    )

    return state


def _validate_multi_agent_inputs(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    analyze_pdb_tool,
    logger
) -> Dict[str, Any]:
    """
    Validate inputs for a multi-agent workflow.

    Only validates what the FIRST agent in the pipeline needs.
    Later agents rely on outputs from prior agents (e.g., reporter uses
    analysis outputs that don't exist yet at validation time).
    """
    from agentic.utils import log_agent_action

    agent_list = state.get("agent_list") or []
    logger.info(f"INPUT_VALIDATION: Multi-agent validation for agents: {agent_list}")

    if not agent_list:
        state["errors"].append("No agents specified in agent_list for multi-agent workflow")
        return state

    _PDB_REQUIRING = {"preprocess", "simsetup", "hpcjob"}
    _TRAJ_REQUIRING = {"analysis"}
    _REPORT_REQUIRING = {"reporter"}

    # Validate based on FIRST agent only
    first_agent = agent_list[0]
    logger.info(f"INPUT_VALIDATION: Validating for first agent: {first_agent}")

    if first_agent in _PDB_REQUIRING:
        state = _analyze_pdb_if_available(state, user_goal, working_directory, analyze_pdb_tool, logger)
        state = _validate_pdb_based_task(state, user_goal, working_directory, logger)
    elif first_agent in _TRAJ_REQUIRING:
        state = _validate_analysis_files(state, user_goal, working_directory, logger)
    elif first_agent in _REPORT_REQUIRING:
        state = _validate_reporter_files(state, user_goal, working_directory, logger)

    multi_details = {
        "agent_list": agent_list,
        "validated_for": first_agent,
    }
    sys_info = state.get("system_info")
    if sys_info and sys_info.get("success"):
        multi_details["system_summary"] = sys_info.get("summary", "")
        multi_details["total_atoms"] = sys_info.get("total_atoms", 0)
        multi_details["components"] = sys_info.get("components", {})
        if sys_info.get("trajectory"):
            traj = sys_info["trajectory"]
            multi_details["n_frames"] = traj.get("n_frames", 0)
            multi_details["total_time_ns"] = traj.get("total_time_ns", 0)

    log_agent_action(
        agent_name="supervisor.input_validation",
        action="Multi-Agent Input Validation Complete",
        details=multi_details
    )
    return state
