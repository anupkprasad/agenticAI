"""
Analysis Agent Tools - Thin wrapper for modular analysis tools

Exposes stable, reusable @tool functions from src/analysis/ for:
- RMSD (Root Mean Square Deviation) calculation
- RMSF (Root Mean Square Fluctuation) calculation
- Radius of gyration analysis
- Energy analysis
- Trajectory metrics extraction
- Data visualization and plotting

This module follows the pattern of agentic/hpc/tools.py and agentic/simsetup/tools.py:
actual tool implementations are in src/analysis/* and imported here.

Additionally, dynamically loads programmer-generated tools from working_dir/programmer/
to make them available for analysis workflows.
"""
import os
import logging
import inspect
from pathlib import Path
from typing import Dict, Any, Optional, List

# Import modular tools from src/analysis/
from src.analysis.rmsd_calculator import calculate_rmsd
from src.analysis.rmsf_calculator import calculate_rmsf
from src.analysis.gyration_calculator import calculate_radius_of_gyration
from src.analysis.energy_analyzer import analyze_energy, extract_trajectory_metrics
from src.analysis.data_plotter import (
    plot_data, plot_multipanel, plot_combined_data, plot_3d,
    plot_md_data, plot_md_multipanel,  # backward-compat aliases
)
from src.analysis.summary_logger import initialize_summary_file, generate_summary_report
from src.analysis.dssp_analyzer import analyze_secondary_structure
from src.analysis.sasa_calculator import calculate_sasa, plot_sasa
from src.analysis.com_distance_calculator import calculate_com_distance, calculate_ligand_pocket_distance
from src.analysis.proximity_analyzer import identify_nearby_residues, calculate_min_heavy_atom_distance
from src.analysis.interface_analyzer import calculate_hbond_occupancy, calculate_salt_bridge_distances
from src.analysis.dccm_calculator import (
    calculate_dccm,
    plot_dccm_comparison,
    plot_dccm_difference,
)
from src.analysis.binding_site_analyzer import (
    calculate_protein_ligand_contacts,
    calculate_pocket_sasa,
    analyze_ligand_residence,
    calculate_pocket_rmsf,
    calculate_ligand_rmsf,
)
from src.analysis.classification_collector import collect_classification_features_table
from src.analysis.classification_clustering import (
    cluster_classification_features,
    plot_cluster_feature_trajectories,
    plot_cluster_rmsf_profiles,
    CLUSTER_TRAJECTORY_METRIC_GROUPS,
    CLUSTER_RMSF_PROFILE_GROUPS,
)
from src.analysis.pca_analyzer import (
    calculate_trajectory_pca,
    plot_pca_projection,
    calculate_free_energy_landscape,
    analyze_fel_landscape_features,
    export_fel_basin_structures,
    collect_fel_features_table,
    apply_pca_tool_defaults,
    PCA_TOOL_DEFAULTS,
)
from src.analysis.trajectory_wrapper import wrap_trajectory
from src.analysis.combined_analysis import (
    collect_metric_files,
    plot_combined_overlay,
    compute_comparison_table,
    run_combined_analysis,
    run_combined_dccm_analysis,
    run_combined_dccm_difference,
    plot_combined_rmsf_segment_bars,
    run_combined_rmsf_segment_analysis,
    run_combined_com_distance_analysis,
    pair_apo_holo_simulations,
    is_holo_simulation,
    plot_rmsf_apo_holo_comparison,
    run_combined_rmsf_apo_holo_analysis,
    run_combined_dccm_apo_holo_analysis,
    run_combined_rmsf_segment_apo_holo_analysis,
    run_combined_binding_rmsf_overlay,
)
from src.analysis.phylo_tree import (
    build_sequence_phylo_tree,
    build_structure_phylo_tree,
)
from src.analysis.consensus_alignment import build_consensus_sequence_alignment
from src.analysis.reference_landscape import (
    fit_reference_pca_model,
    project_simulations_reference_pca,
    build_shared_reference_fel_landscapes,
    cluster_reference_fel_landscapes,
    run_reference_landscape_pipeline,
)
from src.analysis.consensus_pocket import (
    define_reference_consensus_pocket,
    map_consensus_pocket_residues,
    calculate_consensus_pocket_metrics,
    run_consensus_pocket_metrics_batch,
)
from src.analysis.msa_plotting import plot_reference_msa_alignment

# Import dynamic tool loader for programmer-generated tools
from agentic.utils import get_dynamic_tool_loader

# Export all tools
__all__ = [
    "calculate_rmsd",
    "calculate_rmsf",
    "calculate_radius_of_gyration",
    "calculate_sasa",
    "plot_sasa",
    "analyze_energy",
    "extract_trajectory_metrics",
    "analyze_secondary_structure",
    "plot_data",
    "plot_multipanel",
    "plot_combined_data",
    "plot_3d",
    "plot_md_data",
    "plot_md_multipanel",
    "calculate_com_distance",
    "calculate_ligand_pocket_distance",
    "identify_nearby_residues",
    "calculate_min_heavy_atom_distance",
    "calculate_hbond_occupancy",
    "calculate_salt_bridge_distances",
    "calculate_dccm",
    "plot_dccm_comparison",
    "plot_dccm_difference",
    "wrap_trajectory",
    "calculate_trajectory_pca",
    "plot_pca_projection",
    "calculate_free_energy_landscape",
    "analyze_fel_landscape_features",
    "export_fel_basin_structures",
    "calculate_protein_ligand_contacts",
    "calculate_pocket_sasa",
    "analyze_ligand_residence",
    "calculate_pocket_rmsf",
    "calculate_ligand_rmsf",
    # Combined (multi-sim) tools
    "collect_metric_files",
    "plot_combined_overlay",
    "compute_comparison_table",
    "run_combined_analysis",
    "run_combined_dccm_analysis",
    "run_combined_dccm_difference",
    "plot_combined_rmsf_segment_bars",
    "run_combined_rmsf_segment_analysis",
    "run_combined_com_distance_analysis",
    "pair_apo_holo_simulations",
    "is_holo_simulation",
    "plot_rmsf_apo_holo_comparison",
    "run_combined_rmsf_apo_holo_analysis",
    "run_combined_dccm_apo_holo_analysis",
    "run_combined_rmsf_segment_apo_holo_analysis",
    "build_sequence_phylo_tree",
    "build_structure_phylo_tree",
    "build_consensus_sequence_alignment",
    "fit_reference_pca_model",
    "project_simulations_reference_pca",
    "build_shared_reference_fel_landscapes",
    "cluster_reference_fel_landscapes",
    "run_reference_landscape_pipeline",
    "define_reference_consensus_pocket",
    "map_consensus_pocket_residues",
    "calculate_consensus_pocket_metrics",
    "run_consensus_pocket_metrics_batch",
    "plot_reference_msa_alignment",
    "AnalysisToolExecutor",
    "get_analysis_tools",
    "get_tool_metadata",
    "COMBINED_ANALYSIS_TOOL_NAMES",
    "is_combined_analysis_tool",
    "initialize_summary_file",
    "generate_summary_report"
]

logger = logging.getLogger(__name__)

# Cross-simulation tools — only for the combined_analysis phase after all per-sim runs.
# Must NOT be exposed to the planner or analysis LLM during individual simulation workflows.
COMBINED_ANALYSIS_TOOL_NAMES = frozenset({
    "collect_metric_files",
    "plot_combined_overlay",
    "compute_comparison_table",
    "run_combined_analysis",
    "run_combined_dccm_analysis",
    "run_combined_dccm_difference",
    "plot_combined_rmsf_segment_bars",
    "run_combined_rmsf_segment_analysis",
    "run_combined_com_distance_analysis",
    "plot_rmsf_apo_holo_comparison",
    "run_combined_rmsf_apo_holo_analysis",
    "run_combined_dccm_apo_holo_analysis",
    "run_combined_rmsf_segment_apo_holo_analysis",
    "run_combined_binding_rmsf_overlay",
    "collect_fel_features_table",
    "collect_classification_features_table",
    "cluster_classification_features",
    "plot_cluster_feature_trajectories",
    "plot_cluster_rmsf_profiles",
    "build_sequence_phylo_tree",
    "build_structure_phylo_tree",
    "build_consensus_sequence_alignment",
    "fit_reference_pca_model",
    "project_simulations_reference_pca",
    "build_shared_reference_fel_landscapes",
    "cluster_reference_fel_landscapes",
    "run_reference_landscape_pipeline",
    "define_reference_consensus_pocket",
    "map_consensus_pocket_residues",
    "calculate_consensus_pocket_metrics",
    "run_consensus_pocket_metrics_batch",
    "plot_reference_msa_alignment",
})

_PER_SIM_ANALYSIS_TOOLS = [
    calculate_rmsd,
    calculate_rmsf,
    calculate_radius_of_gyration,
    calculate_sasa,
    plot_sasa,
    analyze_energy,
    extract_trajectory_metrics,
    analyze_secondary_structure,
    plot_md_data,
    plot_md_multipanel,
    plot_combined_data,
    calculate_com_distance,
    calculate_ligand_pocket_distance,
    identify_nearby_residues,
    calculate_min_heavy_atom_distance,
    calculate_hbond_occupancy,
    calculate_salt_bridge_distances,
    calculate_dccm,
    plot_dccm_comparison,
    plot_dccm_difference,
    wrap_trajectory,
    calculate_trajectory_pca,
    plot_pca_projection,
    calculate_free_energy_landscape,
    analyze_fel_landscape_features,
    export_fel_basin_structures,
    calculate_protein_ligand_contacts,
    calculate_pocket_sasa,
    analyze_ligand_residence,
    calculate_pocket_rmsf,
    calculate_ligand_rmsf,
]

_COMBINED_ANALYSIS_TOOLS = [
    collect_metric_files,
    plot_combined_overlay,
    compute_comparison_table,
    run_combined_analysis,
    run_combined_dccm_analysis,
    run_combined_dccm_difference,
    plot_combined_rmsf_segment_bars,
    run_combined_rmsf_segment_analysis,
    run_combined_com_distance_analysis,
    plot_rmsf_apo_holo_comparison,
    run_combined_rmsf_apo_holo_analysis,
    run_combined_dccm_apo_holo_analysis,
    run_combined_rmsf_segment_apo_holo_analysis,
    run_combined_binding_rmsf_overlay,
    collect_fel_features_table,
    collect_classification_features_table,
    cluster_classification_features,
    plot_cluster_feature_trajectories,
    plot_cluster_rmsf_profiles,
    build_sequence_phylo_tree,
    build_structure_phylo_tree,
    build_consensus_sequence_alignment,
    fit_reference_pca_model,
    project_simulations_reference_pca,
    build_shared_reference_fel_landscapes,
    cluster_reference_fel_landscapes,
    run_reference_landscape_pipeline,
    define_reference_consensus_pocket,
    map_consensus_pocket_residues,
    calculate_consensus_pocket_metrics,
    run_consensus_pocket_metrics_batch,
    plot_reference_msa_alignment,
]


def is_combined_analysis_tool(tool_name: str) -> bool:
    """Return True if *tool_name* is a cross-simulation combined-analysis tool."""
    return tool_name in COMBINED_ANALYSIS_TOOL_NAMES


def get_analysis_tools(include_combined: bool = False) -> list:
    """
    Get analysis @tool functions for LLM binding and tool registry.

    Args:
        include_combined: When True, include cross-simulation combined-analysis tools.
            Default False — per-simulation planner/analysis agents must not see them.

    Returns:
        List of StructuredTool objects ready for LLM use
    """
    if include_combined:
        return _PER_SIM_ANALYSIS_TOOLS + _COMBINED_ANALYSIS_TOOLS
    return list(_PER_SIM_ANALYSIS_TOOLS)


def get_tool_metadata(
    working_directory: Optional[str] = None,
    include_combined: bool = False,
) -> Dict[str, Dict[str, Any]]:
    """
    Dynamically extract metadata from all @tool functions.
    This provides tool information for the planner agent.
    
    Args:
        working_directory: Base working directory (e.g. 'work_di'). Used to locate programmer-generated tools.
        include_combined: When True, include cross-simulation combined-analysis tools.
    
    Returns:
        Dict mapping tool names to their metadata (description, args, etc.)
    """
    tools = get_analysis_tools(include_combined=include_combined)
    metadata = {}
    
    for tool in tools:
        # StructuredTool has .name, .description, .args_schema attributes
        tool_info = {
            "name": tool.name,
            "description": tool.description,
            "args": {},
        }
        
        # Extract argument schema if available
        if hasattr(tool, 'args_schema') and tool.args_schema:
            schema = tool.args_schema.schema()
            if 'properties' in schema:
                tool_info["args"] = {
                    arg_name: {
                        "type": arg_props.get("type", "string"),
                        "description": arg_props.get("description", ""),
                        "required": arg_name in schema.get("required", []),
                    }
                    for arg_name, arg_props in schema['properties'].items()
                }
        
        metadata[tool.name] = tool_info
    
    # Also include programmer-generated tools
    try:
        from agentic.utils import get_dynamic_tool_loader
        
        # MUST use refresh=True to get newly created tools
        programmer_dir = str(Path(working_directory) / "programmer") if working_directory else "working_dir/programmer"
        tool_loader = get_dynamic_tool_loader(programmer_dir=programmer_dir, refresh=True)
        programmer_tools_metadata = tool_loader.get_tool_metadata_list()
        
        for prog_tool_meta in programmer_tools_metadata:
            tool_name = prog_tool_meta.get("name", "unknown")
            
            # Convert programmer tool metadata to analysis tool metadata format
            tool_info = {
                "name": tool_name,
                "description": prog_tool_meta.get("description", "Programmer-generated tool"),
                "args": {}
            }
            
            # Convert parameters format
            params = prog_tool_meta.get("parameters", {})
            for param_name, param_details in params.items():
                tool_info["args"][param_name] = {
                    "type": param_details.get("type", "string"),
                    "description": param_details.get("description", ""),
                    "required": param_details.get("required", False),
                }
            
            metadata[tool_name] = tool_info
            logger.info(f"Included programmer-generated tool in metadata: {tool_name}")
    
    except Exception as e:
        logger.warning(f"Could not load programmer-generated tools in get_tool_metadata: {e}")
    
    return metadata


class AnalysisToolExecutor:
    """
    Executor class for analysis agent tools.
    
    Provides a unified interface for executing MD analysis tools with proper
    configuration management, error handling, and result aggregation.
    
    Similar to HPCToolExecutor and SimulationSetupToolExecutor.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize analysis tool executor.
        
        Args:
            config: Analysis configuration (output paths, default selections, etc.)
        """
        self.config = config or {}
        include_combined = self.config.get("include_combined_tools", False)
        
        # Core analysis tools (per-simulation only unless include_combined_tools=True)
        self.tools = {
            "calculate_rmsd": calculate_rmsd,
            "calculate_rmsf": calculate_rmsf,
            "calculate_radius_of_gyration": calculate_radius_of_gyration,
            "calculate_sasa": calculate_sasa,
            "plot_sasa": plot_sasa,
            "analyze_energy": analyze_energy,
            "extract_trajectory_metrics": extract_trajectory_metrics,
            "analyze_secondary_structure": analyze_secondary_structure,
            "plot_data": plot_data,
            "plot_multipanel": plot_multipanel,
            "plot_combined_data": plot_combined_data,
            "plot_3d": plot_3d,
            # backward-compat aliases
            "plot_md_data": plot_md_data,
            "plot_md_multipanel": plot_md_multipanel,
            "calculate_com_distance": calculate_com_distance,
            "calculate_ligand_pocket_distance": calculate_ligand_pocket_distance,
            "identify_nearby_residues": identify_nearby_residues,
            "calculate_min_heavy_atom_distance": calculate_min_heavy_atom_distance,
            "calculate_hbond_occupancy": calculate_hbond_occupancy,
            "calculate_salt_bridge_distances": calculate_salt_bridge_distances,
            "calculate_dccm": calculate_dccm,
            "plot_dccm_comparison": plot_dccm_comparison,
            "plot_dccm_difference": plot_dccm_difference,
            "wrap_trajectory": wrap_trajectory,
            "calculate_trajectory_pca": calculate_trajectory_pca,
            "plot_pca_projection": plot_pca_projection,
            "calculate_free_energy_landscape": calculate_free_energy_landscape,
            "analyze_fel_landscape_features": analyze_fel_landscape_features,
            "export_fel_basin_structures": export_fel_basin_structures,
            "calculate_protein_ligand_contacts": calculate_protein_ligand_contacts,
            "calculate_pocket_sasa": calculate_pocket_sasa,
            "analyze_ligand_residence": analyze_ligand_residence,
            "calculate_pocket_rmsf": calculate_pocket_rmsf,
            "calculate_ligand_rmsf": calculate_ligand_rmsf,
        }
        if include_combined:
            self.tools.update({
                "collect_metric_files": collect_metric_files,
                "plot_combined_overlay": plot_combined_overlay,
                "compute_comparison_table": compute_comparison_table,
                "run_combined_analysis": run_combined_analysis,
                "run_combined_dccm_analysis": run_combined_dccm_analysis,
                "run_combined_dccm_difference": run_combined_dccm_difference,
                "plot_combined_rmsf_segment_bars": plot_combined_rmsf_segment_bars,
                "run_combined_rmsf_segment_analysis": run_combined_rmsf_segment_analysis,
                "run_combined_com_distance_analysis": run_combined_com_distance_analysis,
                "plot_rmsf_apo_holo_comparison": plot_rmsf_apo_holo_comparison,
                "run_combined_rmsf_apo_holo_analysis": run_combined_rmsf_apo_holo_analysis,
                "run_combined_dccm_apo_holo_analysis": run_combined_dccm_apo_holo_analysis,
                "run_combined_rmsf_segment_apo_holo_analysis": run_combined_rmsf_segment_apo_holo_analysis,
                "run_combined_binding_rmsf_overlay": run_combined_binding_rmsf_overlay,
                "collect_fel_features_table": collect_fel_features_table,
                "collect_classification_features_table": collect_classification_features_table,
                "cluster_classification_features": cluster_classification_features,
                "plot_cluster_feature_trajectories": plot_cluster_feature_trajectories,
                "plot_cluster_rmsf_profiles": plot_cluster_rmsf_profiles,
                "build_sequence_phylo_tree": build_sequence_phylo_tree,
                "build_structure_phylo_tree": build_structure_phylo_tree,
                "build_consensus_sequence_alignment": build_consensus_sequence_alignment,
                "fit_reference_pca_model": fit_reference_pca_model,
                "project_simulations_reference_pca": project_simulations_reference_pca,
                "build_shared_reference_fel_landscapes": build_shared_reference_fel_landscapes,
                "cluster_reference_fel_landscapes": cluster_reference_fel_landscapes,
                "run_reference_landscape_pipeline": run_reference_landscape_pipeline,
                "define_reference_consensus_pocket": define_reference_consensus_pocket,
                "map_consensus_pocket_residues": map_consensus_pocket_residues,
                "calculate_consensus_pocket_metrics": calculate_consensus_pocket_metrics,
                "run_consensus_pocket_metrics_batch": run_consensus_pocket_metrics_batch,
                "plot_reference_msa_alignment": plot_reference_msa_alignment,
            })
        
        # Record built-in tool names BEFORE loading programmer tools
        # so _auto_log_summary can skip tools that already self-log
        self._builtin_tool_names = set(self.tools.keys())
        
        # Setup working directory BEFORE loading programmer tools
        self.working_dir = self.config.get("working_directory", "./working_dir/analysis")
        os.makedirs(self.working_dir, exist_ok=True)
        
        # Load programmer-generated tools dynamically (needs working_dir to be set)
        self._load_programmer_tools()
        
        # Initialize analysis summary file
        try:
            summary_path = initialize_summary_file(self.working_dir)
            logger.info(f"Analysis summary file initialized: {summary_path}")
        except Exception as e:
            logger.warning(f"Failed to initialize summary file: {e}")
        
        logger.info(f"AnalysisToolExecutor initialized with {len(self.tools)} tools (working_dir: {self.working_dir})")
    
    def _wrap_tool_for_working_dir(self, tool_func, tool_name: str):
        """
        Wrap a programmer-generated tool to execute in the agent's working directory.
        This ensures all file outputs go to the correct location (e.g., working_dir/analysis).
        
        Args:
            tool_func: The tool function to wrap
            tool_name: Name of the tool (for logging)
            
        Returns:
            Wrapped function that executes in the agent's working directory
        """
        from functools import wraps
        
        # Get the actual function if it's a StructuredTool
        actual_func = tool_func.func if hasattr(tool_func, 'func') else tool_func
        
        @wraps(actual_func)
        def wrapped_tool(**kwargs):
            """
            Execute tool in the agent's working directory context.
            Changes to working_dir before execution and restores original directory after.
            """
            import os
            original_dir = os.getcwd()
            try:
                # Change to agent's working directory
                os.chdir(self.working_dir)
                logger.debug(f"Executing {tool_name} in directory: {self.working_dir}")
                
                # Execute the tool
                if hasattr(tool_func, 'func'):
                    result = tool_func.func(**kwargs)
                elif hasattr(tool_func, 'invoke'):
                    result = tool_func.invoke(kwargs)
                else:
                    result = tool_func(**kwargs)
                
                return result
            finally:
                # Always restore original directory
                os.chdir(original_dir)
        
        # Preserve StructuredTool attributes if needed
        if hasattr(tool_func, 'name'):
            wrapped_tool.name = tool_func.name
        if hasattr(tool_func, 'description'):
            wrapped_tool.description = tool_func.description
        if hasattr(tool_func, 'args_schema'):
            wrapped_tool.args_schema = tool_func.args_schema
            
        return wrapped_tool
    
    def _load_programmer_tools(self):
        """Load dynamically generated tools from programmer agent."""
        try:
            # Derive programmer dir from working_dir (e.g. work_di/analysis -> work_di/programmer)
            programmer_dir = str(Path(self.working_dir).parent / "programmer") if self.working_dir else None
            tool_loader = get_dynamic_tool_loader(programmer_dir=programmer_dir, refresh=True) if programmer_dir else get_dynamic_tool_loader(refresh=True)
            programmer_tools = tool_loader.get_tools_for_agent("analysis")
            
            if programmer_tools:
                logger.info(f"Loading {len(programmer_tools)} programmer-generated tools for analysis agent")
                for tool_name, tool_func in programmer_tools.items():
                    # Wrap the tool to execute in the agent's working directory
                    wrapped_tool = self._wrap_tool_for_working_dir(tool_func, tool_name)
                    self.tools[tool_name] = wrapped_tool
                    logger.info(f"  Registered programmer tool: {tool_name} (wrapped for {self.working_dir})")
            else:
                logger.debug("No programmer-generated tools found")
                
        except Exception as e:
            logger.warning(f"Failed to load programmer tools: {e}")
    
    def reload_programmer_tools(self):
        """Reload programmer-generated tools (call after programmer creates new tools)."""
        try:
            programmer_dir = str(Path(self.working_dir).parent / "programmer") if self.working_dir else None
            tool_loader = get_dynamic_tool_loader(programmer_dir=programmer_dir, refresh=True) if programmer_dir else get_dynamic_tool_loader(refresh=True)
            programmer_tools = tool_loader.get_tools_for_agent("analysis")
            
            # Add new tools
            for tool_name, tool_func in programmer_tools.items():
                if tool_name not in self.tools:
                    logger.info(f"Adding new programmer tool: {tool_name}")
                self.tools[tool_name] = tool_func
            
            logger.info(f"Reloaded programmer tools. Total tools: {len(self.tools)}")
            
        except Exception as e:
            logger.error(f"Failed to reload programmer tools: {e}")
    
    def execute(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute an analysis tool with given parameters.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool-specific parameters
            
        Returns:
            Dict with execution result
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}. Available: {list(self.tools.keys())}"
            }
        
        # Normalise common LLM parameter-name mistakes before calling the tool
        _TOOL_SPECIFIC_ALIASES: Dict[str, Dict[str, str]] = {
            "plot_pca_projection": {
                "pca_file": "pca_projections_file",
                "input_file": "pca_projections_file",
            },
            "calculate_free_energy_landscape": {
                "pca_file": "pca_projections_file",
                "input_file": "pca_projections_file",
            },
            "analyze_fel_landscape_features": {
                "pca_file": "pca_projections_file",
            },
            "calculate_trajectory_pca": {
                "output_file": "projections_file",
            },
        }
        _PARAM_ALIASES = {
            "title": "titles",
            "ylabel": "ylabels",  # multipanel expects plural
            "xlabel": "xlabels",  # multipanel expects plural
            "plot_type": "plot_types",  # multipanel expects plural
            "color": "colors",
            "label": "labels",
            "data_file": "data_files",   # LLM often sends singular
            "csv_file": "data_files",    # LLM may use csv_file instead
            "input_file": "data_files",  # another common LLM alias
        }
        tool_func_raw = self.tools[tool_name]
        actual_fn = tool_func_raw.func if hasattr(tool_func_raw, 'func') else tool_func_raw
        try:
            valid_params = set(inspect.signature(actual_fn).parameters.keys())
        except Exception:
            valid_params = None
        
        if valid_params is not None:
            aliases_applied = {}
            for alias, canonical in (_TOOL_SPECIFIC_ALIASES.get(tool_name) or {}).items():
                if alias in kwargs and alias not in valid_params and canonical in valid_params:
                    kwargs[canonical] = kwargs.pop(alias)
                    aliases_applied[alias] = canonical
            for alias, canonical in _PARAM_ALIASES.items():
                if alias in kwargs and alias not in valid_params and canonical in valid_params:
                    val = kwargs.pop(alias)
                    # Wrap scalar in list for list-typed parameters
                    if canonical not in kwargs:
                        kwargs[canonical] = [val] if isinstance(val, str) else val
                    aliases_applied[alias] = canonical
            try:
                from src.analysis.proximity_analyzer import apply_selection_from_files

                kwargs = apply_selection_from_files(kwargs, working_dir=self.working_dir)
            except Exception as exc:
                logger.warning("selection_from_file resolution skipped: %s", exc)
            # Also strip completely unknown kwargs so they don't cause TypeErrors
            unknown = [k for k in kwargs if k not in valid_params]
            for k in unknown:
                logger.warning(f"Dropping unknown parameter '{k}' for tool {tool_name}")
                kwargs.pop(k)
            if aliases_applied:
                logger.info(f"Aliased parameters for {tool_name}: {aliases_applied}")

        try:
            from src.analysis.chain_residue_map import (
                ChainSelectionError,
                ensure_chain_residue_map,
                params_need_chain_map,
                translate_selection_params,
            )

            if tool_name not in {"calculate_sasa", "calculate_pocket_sasa", "wrap_trajectory"} and params_need_chain_map(kwargs):
                chain_map = ensure_chain_residue_map(
                    working_dir=self.working_dir,
                    topology_file=kwargs.get("topology_file") or kwargs.get("topology"),
                )
                kwargs = translate_selection_params(kwargs, chain_map)
        except ChainSelectionError as exc:
            return {"success": False, "error": str(exc)}
        except Exception as exc:
            logger.debug("Chain-map translation skipped for %s: %s", tool_name, exc)

        if tool_name in PCA_TOOL_DEFAULTS:
            user_goal = self.config.get("user_goal") or ""
            before = {k: kwargs.get(k) for k in PCA_TOOL_DEFAULTS[tool_name]}
            kwargs = apply_pca_tool_defaults(tool_name, kwargs, user_goal)
            changed = {
                k: (before.get(k), kwargs[k])
                for k in PCA_TOOL_DEFAULTS[tool_name]
                if before.get(k) is not None and before.get(k) != kwargs[k]
            }
            if changed:
                logger.info(
                    "Applied canonical PCA/FEL defaults for %s (overrode plan params: %s)",
                    tool_name,
                    changed,
                )
            # Defaults may inject params the tool function does not accept (e.g. temperature_k).
            if valid_params is not None:
                for k in [k for k in kwargs if k not in valid_params]:
                    logger.warning(
                        "Dropping PCA-default parameter '%s' for tool %s", k, tool_name
                    )
                    kwargs.pop(k)
        
        try:
            logger.info(f"Executing analysis tool: {tool_name}")
            
            # Execute the tool
            tool_func = self.tools[tool_name]
            
            # Add working directory only if the function signature accepts it
            # ALWAYS force working_dir to agent directory (prevent file leaks)
            # even if the LLM plan supplies a different value
            actual_func = tool_func.func if hasattr(tool_func, 'func') else tool_func
            try:
                sig = inspect.signature(actual_func)
                if 'working_dir' in sig.parameters:
                    kwargs["working_dir"] = self.working_dir
                    logger.debug(f"Forced working_dir={self.working_dir} for {tool_name}")
            except Exception as e:
                logger.debug(f"Could not inspect signature for {tool_name}: {e}")
            
            # StructuredTool objects (from @tool decorator) need special handling
            if hasattr(tool_func, 'func'):
                # @tool decorator wraps function in StructuredTool - use .func
                result = tool_func.func(**kwargs)
            elif hasattr(tool_func, 'invoke'):
                # Alternative: use LangChain's invoke method
                result = tool_func.invoke(kwargs)
            else:
                # Direct function call (backward compatibility)
                result = tool_func(**kwargs)
            
            # Guard against tools that return None instead of a dict
            if result is None:
                logger.warning(f"Tool {tool_name} returned None — missing return statement")
                result = {"success": False, "error": "Tool returned None (missing return statement)"}

            if result.get("success"):
                logger.info(f"Tool {tool_name} completed successfully")
                # ── Auto-log to analysis_summary.jsonl ────────────────
                # Built-in tools (rmsd, rmsf, dssp etc.) self-log via
                # append_analysis_summary().  Only auto-log for
                # programmer-generated tools that don't self-log.
                if tool_name not in self._builtin_tool_names and not result.get("_summary_logged"):
                    self._auto_log_summary(tool_name, kwargs, result)
            else:
                logger.error(f"Tool {tool_name} failed: {result.get('error', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_name}")
            return {
                "success": False,
                "error": f"Tool execution error: {str(e)}"
            }

    def _auto_log_summary(self, tool_name: str, kwargs: Dict, result: Dict) -> None:
        """Write a summary entry for tools that don't self-log.

        Extracts statistics, file paths, and metadata from the tool's
        return dict and appends to analysis_summary.jsonl.
        """
        try:
            from src.analysis.summary_logger import append_analysis_summary

            # Build a human-friendly analysis_type from tool_name
            analysis_type = tool_name.replace("_", " ").replace("calculate ", "").title()

            # Collect numeric values as statistics
            statistics: Dict[str, Any] = {}
            files: Dict[str, str] = {}
            metadata: Dict[str, Any] = {}

            for k, v in result.items():
                if k in ("success", "error", "message", "_summary_logged"):
                    continue
                if isinstance(v, (int, float)):
                    statistics[k] = v
                elif isinstance(v, str) and ("/" in v or "\\" in v):
                    # Looks like a file path
                    files[k] = v
                elif isinstance(v, dict):
                    # Nested dict — flatten scalar values into statistics
                    for nk, nv in v.items():
                        if isinstance(nv, (int, float)):
                            statistics[nk] = nv
                        elif isinstance(nv, str) and ("/" in nv or "\\" in nv):
                            files[nk] = nv

            # Add input files that were passed as kwargs
            _INPUT_KEYS = ("topology_file", "trajectory_file", "energy_file",
                           "topology", "trajectory")
            for ik in _INPUT_KEYS:
                if ik in kwargs and kwargs[ik]:
                    files.setdefault(ik, str(kwargs[ik]))

            # Collect non-numeric/non-path kwargs as metadata
            for k, v in kwargs.items():
                if k in ("working_dir",):
                    continue
                if k in _INPUT_KEYS:
                    continue
                if isinstance(v, (str, int, float, bool, list)):
                    metadata[k] = v

            # Only log if we have something meaningful
            if statistics or files:
                append_analysis_summary(
                    working_dir=self.working_dir,
                    analysis_type=analysis_type,
                    statistics=statistics,
                    files=files,
                    metadata=metadata,
                )
                logger.info(f"Auto-logged summary for {tool_name}: {len(statistics)} stats, {len(files)} files")
        except Exception as e:
            logger.warning(f"Failed to auto-log summary for {tool_name}: {e}")

    def execute_workflow(
        self,
        topology_file: str,
        trajectory_file: str,
        energy_file: Optional[str] = None,
        analyses: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Execute a complete analysis workflow with multiple tools.
        
        Args:
            topology_file: Topology file path
            trajectory_file: Trajectory file path
            energy_file: Optional energy file path
            analyses: List of analyses to perform (default: ["rmsd", "rmsf", "gyration"])
            
        Returns:
            Dict with aggregated results from all analyses
        """
        if analyses is None:
            analyses = ["rmsd", "rmsf", "gyration"]
        
        logger.info(f"Starting analysis workflow with: {', '.join(analyses)}")
        
        results = {}
        errors = []
        
        # Map analysis names to tool names
        analysis_tool_map = {
            "rmsd": "calculate_rmsd",
            "rmsf": "calculate_rmsf",
            "gyration": "calculate_radius_of_gyration",
            "energy": "analyze_energy",
            "metrics": "extract_trajectory_metrics"
        }
        
        for analysis in analyses:
            tool_name = analysis_tool_map.get(analysis)
            if not tool_name:
                logger.warning(f"Unknown analysis type: {analysis}")
                errors.append(f"Unknown analysis: {analysis}")
                continue
            
            # Prepare parameters based on analysis type
            if analysis == "energy":
                if not energy_file:
                    logger.warning("Energy analysis requested but no energy file provided")
                    errors.append("Energy analysis requires energy_file parameter")
                    continue
                params = {
                    "energy_file": energy_file,
                    "output_file": os.path.join(self.working_dir, f"{analysis}.xvg")
                }
            elif analysis == "metrics":
                params = {
                    "trajectory_file": trajectory_file,
                    "topology_file": topology_file,
                    "output_dir": self.working_dir
                }
            else:
                params = {
                    "topology_file": topology_file,
                    "trajectory_file": trajectory_file,
                    "output_file": os.path.join(self.working_dir, f"{analysis}.dat")
                }
            
            # Execute the analysis
            result = self.execute(tool_name, **params)
            results[analysis] = result
            
            if not result.get("success"):
                errors.append(f"{analysis}: {result.get('error', 'Unknown error')}")
        
        # Create summary
        completed = [a for a, r in results.items() if r.get("success")]
        failed = [a for a, r in results.items() if not r.get("success")]
        
        summary = f"Completed {len(completed)}/{len(analyses)} analyses"
        if completed:
            summary += f". Successful: {', '.join(completed)}"
        if failed:
            summary += f". Failed: {', '.join(failed)}"
        
        return {
            "success": len(failed) == 0,
            "analyses_completed": completed,
            "analyses_failed": failed,
            "results": results,
            "output_directory": self.working_dir,
            "summary": summary,
            "errors": errors if errors else None
        }
    
    def get_available_tools(self) -> List[str]:
        """Get list of available analysis tools."""
        return list(self.tools.keys())
    
    def get_tool_description(self, tool_name: str) -> Optional[str]:
        """Get description of a specific tool."""
        if tool_name in self.tools:
            tool_func = self.tools[tool_name]
            return tool_func.__doc__
        return None


def run_complete_analysis(
    topology_file: str,
    trajectory_file: str,
    energy_file: Optional[str] = None,
    working_dir: str = "./working_dir/analysis",
    analyses: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Convenience function to run complete analysis workflow.
    
    Args:
        topology_file: Topology file path
        trajectory_file: Trajectory file path
        energy_file: Optional energy file path
        working_dir: Working directory for outputs
        analyses: List of analyses to perform
        
    Returns:
        Dict with complete analysis results
    """
    config = {"working_directory": working_dir}
    executor = AnalysisToolExecutor(config=config)
    
    return executor.execute_workflow(
        topology_file=topology_file,
        trajectory_file=trajectory_file,
        energy_file=energy_file,
        analyses=analyses
    )
