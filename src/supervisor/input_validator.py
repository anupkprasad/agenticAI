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
    
    # STEP 1: UNIVERSAL PDB VALIDATION (for all task types)
    # Extract and analyze PDB structure if PDB file is mentioned in user goal
    state = _analyze_pdb_if_available(state, user_goal, working_directory, analyze_pdb_tool, logger)
    
    # STEP 2: TASK-SPECIFIC VALIDATION
    # Route to appropriate validation based on task type
    if subtask_type == "analysis_only":
        # Analysis-only tasks: validate trajectory/topology files
        state = _validate_analysis_files(state, user_goal, working_directory, llm_client, config, logger)
    elif subtask_type == "reporter_only":
        # Reporter-only tasks: validate analysis summary files
        state = _validate_reporter_files(state, user_goal, working_directory, llm_client, config, logger)
    elif subtask_type == "multi_agent":
        # Multi-agent: validate based on which agents are involved
        state = _validate_multi_agent_inputs(state, user_goal, working_directory, llm_client, config, logger)
    else:
        # PDB-based tasks: additional setup/preprocessing validation
        state = _validate_pdb_based_task(state, user_goal, working_directory, llm_client, config, logger)
    
    # Set routing
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
    
    If no PDB file is found, continues gracefully (state will have no pdb_analysis).
    """
    from agentic.utils import log_agent_action
    
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
    llm_client,
    config: Dict[str, Any],
    logger
) -> Dict[str, Any]:
    """Additional validation for PDB-based tasks (setup/preprocess/full).
    
    Assumes PDB has already been analyzed by _analyze_pdb_if_available.
    
    NOTE: This function does VALIDATION ONLY. Enrichment happens in supervisor via unified_enricher.
    """
    from agentic.utils import log_agent_action
    from .component_parser import parse_component_selection, validate_feasibility, build_human_summary
    
    # Get PDB analysis from state (set by _analyze_pdb_if_available)
    analysis = state.get("pdb_analysis")
    
    if not analysis:
        error_msg = "PDB analysis not found in state - cannot proceed with setup/preprocessing"
        state["errors"].append(error_msg)
        logger.error(f"INPUT_VALIDATION: {error_msg}")
        return state
    
    pdb_path = state.get("raw_pdb")

    # Step 1: Parse user intent and determine component selection
    component_selection = parse_component_selection(user_goal, analysis)
    state["component_selection"] = component_selection
    logger.info(f"INPUT_VALIDATION: Component selection: {component_selection}")

    # Step 2: Validate feasibility
    validation_result = validate_feasibility(user_goal, analysis, component_selection)
    
    if not validation_result["is_feasible"]:
        for error in validation_result["errors"]:
            state["errors"].append(error)
            logger.error(f"INPUT_VALIDATION: Feasibility error - {error}")
        return state
    
    for warning in validation_result["warnings"]:
        state["warnings"].append(warning)
        logger.warning(f"INPUT_VALIDATION: {warning}")

    # Step 3: Store PDB summary for enrichment (done by supervisor)
    pdb_summary = build_human_summary(analysis)
    state["pdb_summary"] = pdb_summary
    
    logger.info(f"INPUT_VALIDATION: PDB validation complete")
    
    log_agent_action(
        agent_name="supervisor.input_validation",
        action="PDB Input Validation Complete",
        details={
            "original_goal": user_goal[:100],
            "pdb_file": pdb_path,
            "working_directory": working_directory,
            "component_selection": component_selection
        }
    )

    # Log final validation summary
    logger.info(f"  - PDB Analysis: {'✓ Success' if not state.get('warnings') else '⚠ With warnings'}")
    logger.info(f"  - Component Selection: {component_selection}")
    logger.info(f"  - Working Directory: {working_directory}")
    
    return state


def _validate_reporter_files(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    llm_client,
    config: Dict[str, Any],
    logger
) -> Dict[str, Any]:
    """Validate analysis summary files for reporter-only tasks.
    
    NOTE: This function does VALIDATION ONLY. Enrichment happens in supervisor via unified_enricher.
    """
    from agentic.utils import log_agent_action
    
    analysis_output_dir = os.path.join(working_directory, "analysis")
    
    # Step 1: Validate analysis output directory exists
    if not os.path.exists(analysis_output_dir):
        error = f"Analysis output directory not found: {analysis_output_dir}"
        state["errors"].append(error)
        logger.error(f"INPUT_VALIDATION: {error}")
        return state
    
    logger.info(f"INPUT_VALIDATION: ✓ Analysis output directory found: {analysis_output_dir}")
    
    # Step 2: Validate analysis_summary.jsonl file exists
    summary_file = os.path.join(analysis_output_dir, "analysis_summary.jsonl")
    
    if not os.path.exists(summary_file):
        warning = f"Analysis summary file not found: {summary_file}"
        state["warnings"].append(warning)
        logger.warning(f"INPUT_VALIDATION: {warning}")
        logger.warning("INPUT_VALIDATION: Reporter will work with available data files")
    else:
        logger.info(f"INPUT_VALIDATION: ✓ Analysis summary file found: {summary_file}")
    
    # Step 3: Scan available analysis files
    available_files = []
    try:
        for file in os.listdir(analysis_output_dir):
            file_path = os.path.join(analysis_output_dir, file)
            if os.path.isfile(file_path):
                available_files.append(file)
        logger.info(f"INPUT_VALIDATION: Found {len(available_files)} analysis files")
        for i, file in enumerate(available_files[:10], 1):  # Show first 10
            logger.info(f"  {i}. {file}")
    except Exception as e:
        warning = f"Failed to list files in {analysis_output_dir}: {e}"
        state["warnings"].append(warning)
        logger.warning(f"INPUT_VALIDATION: {warning}")
    
    # Step 4: Build file_info dictionary
    file_info = {
        "analysis_output_dir": analysis_output_dir,
        "analysis_summary_file": summary_file if os.path.exists(summary_file) else None,
        "available_files": available_files,
        "total_files": len(available_files)
    }
    
    # Step 5: Store file_info for enrichment (done by supervisor)
    state["reporter_file_info"] = file_info
    
    logger.info(f"INPUT_VALIDATION: Reporter file validation complete")
    
    # Step 6: Set reporter-specific state fields
    state["analysis_directory"] = analysis_output_dir
    state["reporter_validated"] = True
    
    # Enhance pdb_analysis with reporter-specific file info if it exists
    if "pdb_analysis" not in state or not state["pdb_analysis"]:
        # Fallback: create minimal structure if PDB wasn't analyzed
        logger.warning("INPUT_VALIDATION: No PDB analysis found, creating minimal structure")
        state["pdb_analysis"] = {
            "total_atoms": 0,
            "total_residues": 0,
            "components_available": {},
            "human_readable_summary": "N/A"
        }
    
    # Add reporter-specific metadata to existing pdb_analysis
    state["pdb_analysis"]["subtask_type"] = "reporter_only"
    state["pdb_analysis"]["working_directory"] = working_directory
    state["pdb_analysis"]["analysis_output_dir"] = analysis_output_dir
    state["pdb_analysis"]["analysis_summary_file"] = file_info["analysis_summary_file"]
    state["pdb_analysis"]["available_analysis_files"] = available_files
    
    log_agent_action(
        agent_name="supervisor.input_validation",
        action="Reporter-Only Input Validation Complete",
        details={
            "subtask_type": "reporter_only",
            "user_goal": user_goal[:200],
            "analysis_directory": analysis_output_dir,
            "summary_file": file_info["analysis_summary_file"],
            "total_files": len(available_files),
            "working_directory": working_directory
        }
    )
    
    # Log final validation summary
    logger.info(f"  - File Validation: {'✓ Success' if not state.get('errors') else '✗ Failed'}")
    logger.info(f"  - Analysis Directory: {analysis_output_dir}")
    logger.info(f"  - Summary File: {file_info['analysis_summary_file'] or 'Not found'}")
    logger.info(f"  - Available Files: {len(available_files)}")
    logger.info(f"  - Working Directory: {working_directory}")
    logger.info(f"  - User Goal: {user_goal[:80]}...")
    
    return state


def _validate_analysis_files(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    llm_client,
    config: Dict[str, Any],
    logger
) -> Dict[str, Any]:
    """Validate trajectory/topology files for analysis-only tasks.
    
    NOTE: This function does VALIDATION ONLY. Enrichment happens in supervisor via unified_enricher.
    """
    from agentic.utils import log_agent_action
    from .file_extractor import extract_file_names_from_goal
    
    hpc_output_dir = os.path.join(working_directory, "hpc")
    analysis_output_dir = os.path.join(working_directory, "analysis")
    
    # Step 1: Validate HPC output directory exists
    if not os.path.exists(hpc_output_dir):
        error = f"HPC output directory not found: {hpc_output_dir}"
        state["errors"].append(error)
        logger.error(f"INPUT_VALIDATION: {error}")
        return state
    
    logger.info(f"INPUT_VALIDATION: ✓ HPC output directory found: {hpc_output_dir}")
    
    # Step 2: Discover/validate files
    topology_file, trajectory_file, energy_file = extract_file_names_from_goal(
        user_goal, hpc_output_dir
    )
    
    logger.info("INPUT_VALIDATION: File discovery strategy:")
    logger.info("  1. Use explicitly stated files in user goal")
    logger.info("  2. Default to md.* pattern (md.gro, md.xtc, md.edr)")
    logger.info("  3. Auto-discover first available file as fallback")
    
    # If explicit/default files not found, fall back to auto-discovery
    if not topology_file or not trajectory_file:
        logger.info("INPUT_VALIDATION: No explicit/default files found, attempting auto-discovery...")
        
        topology_extensions = [".gro", ".pdb", ".tpr"]
        trajectory_extensions = [".xtc", ".trr"]
        energy_extensions = [".edr"]
        
        try:
            hpc_files = os.listdir(hpc_output_dir)
            
            # Find topology file if not already set
            if not topology_file:
                for ext in topology_extensions:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        topology_file = os.path.join(hpc_output_dir, matching[0])
                        logger.info(f"INPUT_VALIDATION: ⚠ Auto-discovered topology: {matching[0]}")
                        break
            
            # Find trajectory file if not already set
            if not trajectory_file:
                for ext in trajectory_extensions:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        trajectory_file = os.path.join(hpc_output_dir, matching[0])
                        logger.info(f"INPUT_VALIDATION: ⚠ Auto-discovered trajectory: {matching[0]}")
                        break
            
            # Find energy file if not already set (optional)
            if not energy_file:
                for ext in energy_extensions:
                    matching = [f for f in hpc_files if f.endswith(ext)]
                    if matching:
                        energy_file = os.path.join(hpc_output_dir, matching[0])
                        logger.info(f"INPUT_VALIDATION: ⚠ Auto-discovered energy: {matching[0]}")
                        break
                    
        except Exception as e:
            error = f"Failed to list files in {hpc_output_dir}: {e}"
            state["errors"].append(error)
            logger.error(f"INPUT_VALIDATION: {error}")
            return state
    else:
        logger.info(f"INPUT_VALIDATION: ✓ Using explicit/default topology: {os.path.basename(topology_file)}")
        logger.info(f"INPUT_VALIDATION: ✓ Using explicit/default trajectory: {os.path.basename(trajectory_file)}")
        if energy_file:
            logger.info(f"INPUT_VALIDATION: ✓ Using explicit/default energy: {os.path.basename(energy_file)}")
    
    # Store in file_info dict
    file_info = {
        "hpc_output_dir": hpc_output_dir,
        "analysis_output_dir": analysis_output_dir,
        "topology_file": topology_file,
        "trajectory_file": trajectory_file,
        "energy_file": energy_file
    }
    
    # Step 3: Validate that required files were found
    if not file_info["topology_file"]:
        warning = f"No topology file (.gro, .pdb, .tpr) found in {hpc_output_dir}"
        state["warnings"].append(warning)
        logger.warning(f"INPUT_VALIDATION: {warning}")
    
    if not file_info["trajectory_file"]:
        warning = f"No trajectory file (.xtc, .trr) found in {hpc_output_dir}"
        state["warnings"].append(warning)
        logger.warning(f"INPUT_VALIDATION: {warning}")
    
    # Step 4: Store file_info for enrichment (done by supervisor)
    state["file_info"] = file_info
    
    logger.info(f"INPUT_VALIDATION: Analysis file validation complete")
    
    # Step 5: Enhance pdb_analysis with analysis-specific file info
    # Note: pdb_analysis should already exist from _analyze_pdb_if_available
    # We're just adding analysis-specific metadata here
    if "pdb_analysis" not in state or not state["pdb_analysis"]:
        # Fallback: create minimal structure if PDB wasn't analyzed
        logger.warning("INPUT_VALIDATION: No PDB analysis found, creating minimal structure")
        state["pdb_analysis"] = {
            "total_atoms": 0,
            "total_residues": 0,
            "components_available": {},
            "human_readable_summary": "N/A"
        }
    
    # Add analysis-specific metadata to existing pdb_analysis
    state["pdb_analysis"]["subtask_type"] = "analysis_only"
    state["pdb_analysis"]["working_directory"] = working_directory
    state["pdb_analysis"]["hpc_output_dir"] = hpc_output_dir
    state["pdb_analysis"]["analysis_output_dir"] = analysis_output_dir
    state["pdb_analysis"]["topology_file"] = file_info["topology_file"]
    state["pdb_analysis"]["trajectory_file"] = file_info["trajectory_file"]
    state["pdb_analysis"]["energy_file"] = file_info["energy_file"]
    
    # CRITICAL: Set top-level state fields that analysis agent expects
    state["topology"] = file_info["topology_file"]
    state["trajectory_path"] = file_info["trajectory_file"]
    state["energy_file"] = file_info["energy_file"]
    state["hpc_output_directory"] = hpc_output_dir
    
    # Create analysis output directory if it doesn't exist
    os.makedirs(analysis_output_dir, exist_ok=True)
    logger.info(f"INPUT_VALIDATION: ✓ Analysis output directory ready: {analysis_output_dir}")
    
    log_agent_action(
        agent_name="supervisor.input_validation-analysis",
        action="Analysis-Only Input Validation Complete",
        details={
            "subtask_type": "analysis-only",
            "user_goal": user_goal[:200],
            "topology_file": file_info["topology_file"],
            "trajectory_file": file_info["trajectory_file"],
            "energy_file": file_info["energy_file"],
            "hpc_output_directory": hpc_output_dir,
            "working_directory": working_directory
        }
    )
    
    # Log final validation summary
    logger.info(f"  - File Validation: {'✓ Success' if not state.get('errors') else '✗ Failed'}")
    logger.info(f"  - Topology: {file_info['topology_file'] or 'Not found'}")
    logger.info(f"  - Trajectory: {file_info['trajectory_file'] or 'Not found'}")
    logger.info(f"  - Working Directory: {working_directory}")
    logger.info(f"  - User Goal: {user_goal[:80]}...")

    return state


def _validate_multi_agent_inputs(
    state: Dict[str, Any],
    user_goal: str,
    working_directory: str,
    llm_client,
    config: Dict[str, Any],
    logger
) -> Dict[str, Any]:
    """
    Validate inputs for a multi-agent workflow.

    Delegates to each relevant single-agent validator based on agent_list,
    then marks the state as multi_agent_validated.
    """
    from agentic.utils import log_agent_action

    agent_list = state.get("agent_list") or []
    logger.info(f"INPUT_VALIDATION: Multi-agent validation for agents: {agent_list}")

    _PDB_REQUIRING = {"preprocess", "simsetup", "hpcjob"}
    _TRAJ_REQUIRING = {"analysis"}
    _REPORT_REQUIRING = {"reporter"}

    has_pdb_agent = bool(set(agent_list) & _PDB_REQUIRING)
    has_traj_agent = bool(set(agent_list) & _TRAJ_REQUIRING)
    has_reporter_agent = bool(set(agent_list) & _REPORT_REQUIRING)

    if has_pdb_agent:
        # PDB analysis was already done in step 1 of universal validation;
        # run the full PDB-based setup check as well
        logger.info("INPUT_VALIDATION: Multi-agent - running PDB-based validation")
        state = _validate_pdb_based_task(state, user_goal, working_directory, llm_client, config, logger)

    if has_traj_agent:
        # Validate trajectory / topology files for analysis
        logger.info("INPUT_VALIDATION: Multi-agent - running trajectory/topology validation")
        state = _validate_analysis_files(state, user_goal, working_directory, llm_client, config, logger)
        # Mark analysis as validated so the analysis agent can proceed
        state["analysis_validated"] = True

    if has_reporter_agent:
        # Validate analysis summary for reporter
        logger.info("INPUT_VALIDATION: Multi-agent - running reporter file validation")
        state = _validate_reporter_files(state, user_goal, working_directory, llm_client, config, logger)
        # reporter_validated set inside _validate_reporter_files; also set here for safety
        state["reporter_validated"] = True

    # Mark overall multi-agent validation as done
    state["multi_agent_validated"] = True
    logger.info(f"INPUT_VALIDATION: Multi-agent validation complete - agents: {agent_list}")

    log_agent_action(
        agent_name="supervisor.input_validation-multi_agent",
        action="Multi-Agent Input Validation Complete",
        details={
            "agent_list": agent_list,
            "has_pdb_agent": has_pdb_agent,
            "has_traj_agent": has_traj_agent,
            "has_reporter_agent": has_reporter_agent,
        }
    )
    return state
    
    return state
