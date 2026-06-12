"""
Path Utilities for Agent Directory Management

Provides centralized utilities for ensuring agents write only to their designated directories.
All agents should use these utilities to enforce directory isolation.

IMPORTANT: Use SecureFileManager for all file operations to ensure:
- Files only written within working_dir
- All operations tracked in file_registry  
- LLM provides filenames only, not full paths
"""
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


def sanitize_tool_output_params(
    tool_params: Dict[str, Any],
    output_param_names: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Sanitize tool parameters to extract only filenames from LLM-generated paths.
    
    This prevents LLM from specifying full paths for output files. The agent
    will prepend the correct directory during execution.
    
    Args:
        tool_params: Raw tool parameters from LLM (may contain full paths)
        output_param_names: List of output parameter names to sanitize
        
    Returns:
        Sanitized parameters with only filenames for output parameters
        
    Example:
        >>> params = {
        ...     "output_file": "/some/path/result.csv",
        ...     "plot_file": "working_dir/analysis/plot.png",
        ...     "data": 123
        ... }
        >>> sanitize_tool_output_params(params)
        {"output_file": "result.csv", "plot_file": "plot.png", "data": 123}
    """
    if output_param_names is None:
        # Default set of output parameters that should be sanitized
        output_param_names = [
            "output_file", "output_path", "output_prefix",
            "plot_file", "figure_path", "figure_file",
            "csv_file", "dat_file", "xvg_file",
            "output_csv", "output_fig", "output_image",
            "save_path", "save_file"
        ]
    
    sanitized = tool_params.copy()
    
    for param_name in output_param_names:
        if param_name in sanitized and sanitized[param_name]:
            original = str(sanitized[param_name])
            
            # Extract just the filename
            filename_only = Path(original).name
            
            if filename_only != original:
                logger.debug(
                    f"Sanitized {param_name}: '{original}' -> '{filename_only}'"
                )
                sanitized[param_name] = filename_only
    
    return sanitized


def normalize_to_filename(path_or_filename: str) -> str:
    """
    Extract just the filename from a path string.
    
    This ensures that agents only receive filenames, never full paths,
    preventing accidental writes to wrong directories.
    
    Args:
        path_or_filename: Either a full path or just a filename
        
    Returns:
        Just the filename without directory components
        
    Examples:
        >>> normalize_to_filename("/path/to/file.txt")
        "file.txt"
        >>> normalize_to_filename("working_dir/analysis/output.png")
        "output.png"
        >>> normalize_to_filename("simple.dat")
        "simple.dat"
    """
    return Path(path_or_filename).name


def normalize_tool_params_for_agent(
    tool_params: Dict[str, Any],
    agent_working_dir: str,
    param_names: Optional[list] = None
) -> Dict[str, Any]:
    """
    Normalize tool parameters to ensure file paths only contain filenames.
    
    This is the main function agents should call to prepare parameters before
    tool execution. It extracts filenames from any path parameters and will
    prepend the agent's working directory at execution time.
    
    Args:
        tool_params: Raw tool parameters from planner (may contain full paths)
        agent_working_dir: The agent's designated working directory
        param_names: List of parameter names to normalize. If None, uses default set.
        
    Returns:
        Normalized parameters with only filenames (paths relative to working_dir)
        
    Example:
        >>> params = {"output_file": "working_dir/hpc/result.csv", "data": 123}
        >>> normalize_tool_params_for_agent(params, "working_dir/analysis")
        {"output_file": "result.csv", "data": 123}
    """
    if param_names is None:
        # Default set of parameters that typically contain file paths
        param_names = [
            "output_file", "output_path", "output_dir",
            "input_file", "input_path",
            "pdb_file", "gro_file", "top_file",
            "trajectory_file", "topology_file",
            "protein_output", "ligand_output", "ion_output",
            "figure_path", "plot_file", "csv_file", "dat_file"
        ]
    
    normalized_params = tool_params.copy()
    
    for param_name in param_names:
        if param_name in normalized_params and normalized_params[param_name]:
            original_value = str(normalized_params[param_name])
            
            # Skip if it's already just a filename (no directory separators)
            if '/' not in original_value and os.sep not in original_value:
                continue
            
            # Extract filename
            filename = normalize_to_filename(original_value)
            normalized_params[param_name] = filename
            
            logger.debug(f"Normalized {param_name}: {original_value} -> {filename}")
    
    return normalized_params


def validate_output_in_agent_directory(
    output_path: str,
    agent_working_dir: str,
    agent_name: str = "agent"
) -> bool:
    """
    Validate that an output file path is within the agent's working directory.
    
    Use this after tool execution to verify outputs went to the correct location.
    
    Args:
        output_path: Path to validate
        agent_working_dir: Expected working directory for this agent
        agent_name: Name of agent (for logging)
        
    Returns:
        True if path is within agent directory, False otherwise
    """
    try:
        output_abs = Path(output_path).resolve()
        agent_dir_abs = Path(agent_working_dir).resolve()
        
        # Check if output is within agent directory
        try:
            output_abs.relative_to(agent_dir_abs)
            return True
        except ValueError:
            logger.warning(
                f"{agent_name}: Output file {output_path} is NOT in agent directory {agent_working_dir}"
            )
            return False
            
    except Exception as e:
        logger.error(f"Error validating output path {output_path}: {e}")
        return False


def ensure_agent_directory_exists(base_working_dir: str, agent_name: str) -> str:
    """
    Create and return the full path to an agent's working directory.
    
    Args:
        base_working_dir: Base working directory (e.g., "working_dir")
        agent_name: Agent name (e.g., "analysis", "simsetup", "preprocess", "hpc", "programmer")
        
    Returns:
        Full path to agent's directory
        
    Example:
        >>> ensure_agent_directory_exists("working_dir", "analysis")
        "/path/to/workspace/working_dir/analysis"
    """
    agent_dir = str(Path(base_working_dir) / agent_name)
    os.makedirs(agent_dir, exist_ok=True)
    logger.debug(f"Ensured directory exists: {agent_dir}")
    return agent_dir


def resolve_preprocess_pdb_path(
    filename: str,
    preprocess_dir: str,
    file_alias_map: Optional[Dict[str, str]] = None,
    current_pdb: Optional[str] = None,
    extra_search_dirs: Optional[List[str]] = None,
) -> str:
    """
    Resolve a PDB filename for preprocessing tools (including structure remodel).

    Handles LLM-invented names like ``chain_a_6VC0_protein.pdb`` after
    ``separate_complex_components`` produced ``protein.pdb``.
    """
    if not filename:
        return current_pdb or ""

    file_alias_map = file_alias_map or {}
    clean = normalize_to_filename(filename)

    if filename in file_alias_map:
        return file_alias_map[filename]
    if clean in file_alias_map:
        return file_alias_map[clean]

    preprocess_path = Path(preprocess_dir) / clean
    if preprocess_path.exists():
        return str(preprocess_path)

    search_dirs = [preprocess_dir]
    if extra_search_dirs:
        search_dirs.extend(extra_search_dirs)
    parent = Path(preprocess_dir).parent
    if str(parent) not in search_dirs:
        search_dirs.append(str(parent))

    for root in search_dirs:
        candidate = Path(root) / clean
        if candidate.exists():
            return str(candidate)

    if current_pdb and os.path.isfile(current_pdb):
        current_name = Path(current_pdb).name
        if clean == current_name or clean == "protein.pdb" or clean.endswith("_protein.pdb"):
            return current_pdb

    return str(preprocess_path)


def get_output_path_for_agent(
    filename: str,
    agent_working_dir: str
) -> str:
    """
    Construct full output path for a file in the agent's directory.
    
    Args:
        filename: Just the filename (no path components)
        agent_working_dir: Agent's working directory
        
    Returns:
        Full path to output file
        
    Example:
        >>> get_output_path_for_agent("result.csv", "/workspace/working_dir/analysis")
        "/workspace/working_dir/analysis/result.csv"
    """
    # Ensure we're only using the filename
    filename_only = normalize_to_filename(filename)
    return str(Path(agent_working_dir) / filename_only)


def resolve_input_file_path(
    file_reference: str,
    file_registry: Dict[str, Dict[str, str]],
    fallback_dirs: Optional[list] = None
) -> str:
    """
    Resolve a file reference to an absolute path using file_registry.
    
    This function enables cross-agent file access by looking up registered files
    and returning their absolute paths. Used primarily by analysis agent to find
    trajectory/topology files created by HPC agent.
    
    Args:
        file_reference: Filename or partial path to resolve
        file_registry: State file_registry mapping paths to metadata
        fallback_dirs: Optional list of directories to search if not in registry
        
    Returns:
        Absolute path to the file
        
    Raises:
        FileNotFoundError: If file cannot be found in registry or fallback dirs
        
    Example:
        >>> registry = {
        ...     "/workspace/working_dir/hpc/md.xtc": {
        ...         "type": "trajectory", "stage": "hpc", "description": "MD trajectory"
        ...     }
        ... }
        >>> resolve_input_file_path("md.xtc", registry)
        "/workspace/working_dir/hpc/md.xtc"
    """
    # Extract filename for comparison
    filename = normalize_to_filename(file_reference)
    
    # Search file_registry for matching filename
    for registered_path, metadata in file_registry.items():
        registered_filename = normalize_to_filename(registered_path)
        if registered_filename == filename:
            # Verify file exists
            if Path(registered_path).exists():
                logger.debug(f"Resolved {file_reference} -> {registered_path} (from file_registry)")
                return registered_path
            else:
                logger.warning(f"File in registry but doesn't exist: {registered_path}")
    
    # If not in registry, try fallback directories
    if fallback_dirs:
        for fallback_dir in fallback_dirs:
            candidate_path = Path(fallback_dir) / filename
            if candidate_path.exists():
                logger.debug(f"Resolved {file_reference} -> {candidate_path} (from fallback)")
                return str(candidate_path)
    
    # Try resolving as-is if it's already a path
    ref_path = Path(file_reference)
    if ref_path.exists():
        return str(ref_path.resolve())
    
    raise FileNotFoundError(
        f"Could not resolve file '{file_reference}'. "
        f"Not found in file_registry ({len(file_registry)} entries) "
        f"or fallback directories: {fallback_dirs}"
    )


def resolve_tool_input_paths(
    tool_params: Dict[str, Any],
    file_registry: Dict[str, Dict[str, str]],
    input_param_names: Optional[list] = None,
    fallback_dirs: Optional[list] = None
) -> Dict[str, Any]:
    """
    Resolve input file parameters to absolute paths using file_registry.
    
    This complements normalize_tool_params_for_agent by handling INPUT files
    that need to be resolved to absolute paths for cross-directory access.
    
    Args:
        tool_params: Tool parameters containing file references
        file_registry: State file_registry for path lookups
        input_param_names: List of input parameter names to resolve
        fallback_dirs: Directories to search if file not in registry
        
    Returns:
        Updated parameters with absolute paths for input files
        
    Example:
        >>> params = {"trajectory": "md.xtc", "topology": "md.gro", "output": "dssp.csv"}
        >>> registry = {"/workspace/working_dir/hpc/md.xtc": {...}, ...}
        >>> resolve_tool_input_paths(params, registry, ["trajectory", "topology"])
        {"trajectory": "/workspace/working_dir/hpc/md.xtc", 
         "topology": "/workspace/working_dir/hpc/md.gro",
         "output": "dssp.csv"}
    """
    if input_param_names is None:
        # Default input parameters that need absolute paths
        input_param_names = [
            "trajectory", "trajectory_file", "traj", "xtc_file",
            "topology", "topology_file", "tpr_file", "gro_file",
            "structure", "structure_file",
            "energy_file", "edr_file",
            "input_file", "input_path"
        ]
    
    resolved_params = tool_params.copy()
    
    for param_name in input_param_names:
        if param_name in resolved_params and resolved_params[param_name]:
            file_ref = str(resolved_params[param_name])
            
            # Skip if already absolute and exists
            if Path(file_ref).is_absolute() and Path(file_ref).exists():
                continue
            
            try:
                resolved_path = resolve_input_file_path(
                    file_ref, 
                    file_registry, 
                    fallback_dirs
                )
                resolved_params[param_name] = resolved_path
                logger.debug(f"Resolved input {param_name}: {file_ref} -> {resolved_path}")
            except FileNotFoundError as e:
                logger.warning(f"Could not resolve {param_name}={file_ref}: {e}")
                # Keep original value, let tool handle the error
    
    return resolved_params


def get_path_resolution_code_snippet() -> str:
    """
    Return a code snippet for path resolution to include in programmer-generated tools.
    
    This standardizes path handling across all dynamically generated tools,
    ensuring they can handle both relative and absolute paths correctly.
    
    Returns:
        Python code as string to insert into generated tools
    """
    return '''"""Path resolution utilities for cross-directory file access"""
from pathlib import Path

def resolve_input_path(file_ref: str, param_name: str = "input") -> Path:
    """Resolve file reference to absolute path with validation."""
    file_path = Path(file_ref)
    
    # If already absolute and exists, return it
    if file_path.is_absolute():
        if file_path.exists():
            return file_path
        else:
            raise FileNotFoundError(f"{param_name} file not found: {file_ref}")
    
    # Try as relative to current directory
    if file_path.exists():
        return file_path.resolve()
    
    # Try resolving from cwd
    cwd_path = Path.cwd() / file_ref
    if cwd_path.exists():
        return cwd_path
    
    # Try just resolving (may expand relative paths)
    resolved = file_path.resolve()
    if resolved.exists():
        return resolved
    
    raise FileNotFoundError(
        f"{param_name} file not found: {file_ref} "
        f"(tried: {file_path}, {cwd_path}, {resolved})"
    )
'''


def register_file_in_registry(
    file_registry: Dict[str, Dict[str, str]],
    file_path: str,
    file_type: str,
    description: str,
    stage: str
) -> None:
    """
    Register a file in the state file_registry for centralized tracking.
    
    This enables cross-agent file discovery and path resolution. All agents
    should register important output files for downstream use.
    
    Args:
        file_registry: State file_registry dictionary (modified in-place)
        file_path: Absolute or relative path to the file
        file_type: Type classification (e.g., "trajectory", "topology", "coordinates", "energy", "output")
        description: Human-readable description of the file
        stage: Workflow stage that created it (e.g., "preprocess", "simsetup", "hpc", "analysis")
        
    Example:
        >>> registry = {}
        >>> register_file_in_registry(
        ...     registry, 
        ...     "/workspace/working_dir/hpc/md.xtc",
        ...     "trajectory",
        ...     "MD production trajectory",
        ...     "hpc"
        ... )
        >>> registry["/workspace/working_dir/hpc/md.xtc"]
        {'type': 'trajectory', 'description': 'MD production trajectory', 'stage': 'hpc'}
    """
    # Convert to absolute path for consistent registry keys
    abs_path = str(Path(file_path).resolve()) if not Path(file_path).is_absolute() else file_path
    
    file_registry[abs_path] = {
        "type": file_type,
        "description": description,
        "stage": stage
    }
    
    logger.debug(f"Registered file: {abs_path} ({file_type}, {stage})")


