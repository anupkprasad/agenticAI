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
"""
import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

# Import modular tools from src/analysis/
from src.analysis.rmsd_calculator import calculate_rmsd
from src.analysis.rmsf_calculator import calculate_rmsf
from src.analysis.gyration_calculator import calculate_radius_of_gyration
from src.analysis.energy_analyzer import analyze_energy, extract_trajectory_metrics
from src.analysis.data_plotter import plot_md_data, plot_md_multipanel, plot_combined_data
from src.analysis.summary_logger import initialize_summary_file, generate_summary_report

# Export all tools
__all__ = [
    "calculate_rmsd",
    "calculate_rmsf",
    "calculate_radius_of_gyration",
    "analyze_energy",
    "extract_trajectory_metrics",
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
        analyze_energy,
        extract_trajectory_metrics,
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
        self.tools = {
            "calculate_rmsd": calculate_rmsd,
            "calculate_rmsf": calculate_rmsf,
            "calculate_radius_of_gyration": calculate_radius_of_gyration,
            "analyze_energy": analyze_energy,
            "extract_trajectory_metrics": extract_trajectory_metrics,
            "plot_md_data": plot_md_data,
            "plot_md_multipanel": plot_md_multipanel,
            "plot_combined_data": plot_combined_data
        }
        
        # Setup working directory
        self.working_dir = self.config.get("working_directory", "./working_dir/analysis")
        os.makedirs(self.working_dir, exist_ok=True)
        
        # Initialize analysis summary file
        try:
            summary_path = initialize_summary_file(self.working_dir)
            logger.info(f"Analysis summary file initialized: {summary_path}")
        except Exception as e:
            logger.warning(f"Failed to initialize summary file: {e}")
        
        logger.info(f"AnalysisToolExecutor initialized with working_dir: {self.working_dir}")
    
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
            
            # Add working directory if not specified
            if "working_dir" not in kwargs:
                kwargs["working_dir"] = self.working_dir
            
            # Execute the tool
            tool_func = self.tools[tool_name]
            
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
