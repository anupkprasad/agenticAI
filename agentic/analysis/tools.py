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
from src.analysis.data_plotter import plot_md_data, plot_md_multipanel, plot_combined_data
from src.analysis.summary_logger import initialize_summary_file, generate_summary_report
from src.analysis.dssp_analyzer import analyze_secondary_structure
from src.analysis.sasa_calculator import calculate_sasa, plot_sasa

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
    "plot_md_data",
    "plot_md_multipanel",
    "plot_combined_data",
    "AnalysisToolExecutor",
    "get_analysis_tools",
    "get_tool_metadata",
    "initialize_summary_file",
    "generate_summary_report"
]

logger = logging.getLogger(__name__)


def get_analysis_tools() -> list:
    """
    Get all analysis @tool functions for LLM binding and tool registry.
    These StructuredTool objects can be passed directly to LLM.bind_tools()
    
    Returns:
        List of StructuredTool objects ready for LLM use
    """
    return [
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
        plot_combined_data
    ]


def get_tool_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Dynamically extract metadata from all @tool functions.
    This provides tool information for the planner agent.
    
    Returns:
        Dict mapping tool names to their metadata (description, args, etc.)
    """
    tools = get_analysis_tools()
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
        tool_loader = get_dynamic_tool_loader(refresh=True)
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
        
        # Core analysis tools
        self.tools = {
            "calculate_rmsd": calculate_rmsd,
            "calculate_rmsf": calculate_rmsf,
            "calculate_radius_of_gyration": calculate_radius_of_gyration,
            "calculate_sasa": calculate_sasa,
            "plot_sasa": plot_sasa,
            "analyze_energy": analyze_energy,
            "extract_trajectory_metrics": extract_trajectory_metrics,
            "analyze_secondary_structure": analyze_secondary_structure,
            "plot_md_data": plot_md_data,
            "plot_md_multipanel": plot_md_multipanel,
            "plot_combined_data": plot_combined_data
        }
        
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
            tool_loader = get_dynamic_tool_loader(refresh=True)
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
            tool_loader = get_dynamic_tool_loader(refresh=True)
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
        
        try:
            logger.info(f"Executing analysis tool: {tool_name}")
            
            # Execute the tool
            tool_func = self.tools[tool_name]
            
            # Add working directory only if the function signature accepts it
            if "working_dir" not in kwargs:
                # Get the actual function (unwrap StructuredTool if needed)
                actual_func = tool_func.func if hasattr(tool_func, 'func') else tool_func
                
                # Check if function accepts working_dir parameter
                try:
                    sig = inspect.signature(actual_func)
                    if 'working_dir' in sig.parameters:
                        kwargs["working_dir"] = self.working_dir
                        logger.debug(f"Added working_dir parameter for {tool_name}")
                    else:
                        logger.debug(f"Tool {tool_name} does not accept working_dir parameter - skipping")
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
            
            if result.get("success"):
                logger.info(f"Tool {tool_name} completed successfully")
            else:
                logger.error(f"Tool {tool_name} failed: {result.get('error', 'Unknown error')}")
            
            return result
            
        except Exception as e:
            logger.exception(f"Tool execution failed for {tool_name}")
            return {
                "success": False,
                "error": f"Tool execution error: {str(e)}"
            }
    
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
