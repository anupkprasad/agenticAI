"""
HPC Agent Tools - Thin wrapper for modular HPC tools

Exposes stable, reusable @tool functions from src/hpc/ for:
- File copying to HPC working directories
- Simulation time estimation
- SLURM script generation
- Job submission and monitoring
- Results downloading

This module follows the pattern of agentic/simsetup/tools.py:
tools are defined in src/hpc/* and imported here.
"""
import os
import time
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from functools import wraps

# Import modular tools from src/hpc/
from src.hpc.file_copy import copy_simulation_files
from src.hpc.time_estimator import estimate_simulation_time
from src.hpc.script_creator import create_slurm_script
from src.hpc.job_submitter import submit_job
from src.hpc.job_monitor import check_job_status, list_my_slurm_jobs
from src.hpc.results_downloader import download_results

# Export all tools
__all__ = [
    "copy_simulation_files",
    "estimate_simulation_time", 
    "create_slurm_script",
    "submit_job",
    "check_job_status",
    "list_my_slurm_jobs",
    "download_results",
    "HPCToolExecutor"
]

logger = logging.getLogger(__name__)

class HPCToolExecutor:
    """
    Executor class for HPC agent tools.
    
    Similar to SimulationSetupToolExecutor, this class provides a unified
    interface for executing HPC tools with proper configuration management
    and error handling.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize HPC tool executor.
        
        Args:
            config: HPC configuration (ssh, paths, slurm defaults)
        """
        self.config = config or {}
        
        # Set working directory for programmer tool outputs
        paths = self.config.get("paths", {})
        self.working_dir = Path(paths.get("local_hpc_dir", "working_dir/hpc"))
        self.working_dir.mkdir(parents=True, exist_ok=True)
        
        self.tools = {
            "copy_simulation_files": copy_simulation_files,
            "estimate_simulation_time": estimate_simulation_time,
            "create_slurm_script": create_slurm_script,
            "submit_job": submit_job,
            "check_job_status": check_job_status,
            "list_my_slurm_jobs": list_my_slurm_jobs,
            "download_results": download_results
        }
        
        # Load programmer-generated tools
        self._load_programmer_tools()
        
        logger.info(f"HPCToolExecutor initialized with {len(self.tools)} tools (working_dir: {self.working_dir})")
    
    def _wrap_tool_for_working_dir(self, tool_func, tool_name: str):
        """
        Wrap a programmer-generated tool to execute in the agent's working directory.
        This ensures all file outputs go to working_dir/hpc.
        
        Args:
            tool_func: The tool function to wrap
            tool_name: Name of the tool (for logging)
            
        Returns:
            Wrapped function that executes in the agent's working directory
        """
        # Get the actual function if it's a StructuredTool
        actual_func = tool_func.func if hasattr(tool_func, 'func') else tool_func
        
        @wraps(actual_func)
        def wrapped_tool(**kwargs):
            """
            Execute tool in the agent's working directory context.
            Changes to working_dir before execution and restores original directory after.
            """
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
            from agentic.utils import get_dynamic_tool_loader
            
            tool_loader = get_dynamic_tool_loader(refresh=True)
            programmer_tools = tool_loader.get_tools_for_agent("hpc")
            
            if programmer_tools:
                logger.info(f"Loading {len(programmer_tools)} programmer-generated tools for hpc agent")
                for tool_name, tool_func in programmer_tools.items():
                    # Wrap the tool to execute in the agent's working directory
                    wrapped_tool = self._wrap_tool_for_working_dir(tool_func, tool_name)
                    self.tools[tool_name] = wrapped_tool
                    logger.info(f"  Registered programmer tool: {tool_name} (wrapped for {self.working_dir})")
            else:
                logger.debug("No programmer-generated tools found")
                
        except Exception as e:
            logger.warning(f"Failed to load programmer tools: {e}")
    
    def execute(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute an HPC tool with given parameters.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool-specific parameters
            
        Returns:
            Dict with execution result
        """
        if tool_name not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        try:
            tool_func = self.tools[tool_name]
            
            # Merge config defaults with provided kwargs
            enriched_kwargs = self._enrich_parameters(tool_name, kwargs)
            
            # Execute tool
            result = tool_func.invoke(enriched_kwargs)
            
            return result
            
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return {
                "success": False,
                "error": f"Tool execution failed: {e}"
            }
    
    def _enrich_parameters(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enrich tool parameters with config defaults.
        
        Args:
            tool_name: Tool name
            params: Original parameters
            
        Returns:
            Enriched parameters
        """
        enriched = params.copy()
        
        # Add SSH config for remote tools
        if tool_name in ["submit_job", "check_job_status", "download_results"]:
            ssh_config = self.config.get("ssh", {})
            if "remote_host" not in enriched and "host" in ssh_config:
                enriched["remote_host"] = ssh_config["host"]
            if "remote_user" not in enriched and "user" in ssh_config:
                enriched["remote_user"] = ssh_config["user"]
            if "ssh_key_path" not in enriched and "key_path" in ssh_config:
                enriched["ssh_key_path"] = ssh_config["key_path"]
        
        # Add path config
        paths = self.config.get("paths", {})
        if tool_name == "copy_simulation_files" and "dest_dir" not in enriched:
            enriched["dest_dir"] = paths.get("local_hpc_dir", "working_dir/hpc")
        if tool_name == "download_results" and "local_dir" not in enriched:
            enriched["local_dir"] = paths.get("local_download_dir", "working_dir/results")
        
        # Add SLURM defaults
        if tool_name == "create_slurm_script":
            slurm_defaults = self.config.get("slurm_defaults", {})
            for key, value in slurm_defaults.items():
                if key not in enriched:
                    enriched[key] = value
            from src.hpc.time_options import resolve_hpc_time_limit

            enriched["time_limit"] = resolve_hpc_time_limit(
                proposed=enriched.get("time_limit"),
            )
        
        return enriched
    
    def get_available_tools(self) -> List[str]:
        """Get list of available tools"""
        return list(self.tools.keys())
