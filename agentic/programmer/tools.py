"""
Programmer Agent Tools - Code Generation Tools
Thin wrapper that exposes modular @tool functions from src/programmer/
"""
import os
import logging
from typing import Dict, Any, Optional, List

# Import modular @tool functions from src/programmer/
from src.programmer.python_generator import generate_python_tool
from src.programmer.tcl_generator import generate_tcl_script
from src.programmer.mdp_generator import generate_mdp_file
from src.programmer.code_validator import validate_python_code, validate_tcl_code

# Export all tools
__all__ = [
    "generate_python_tool",
    "generate_tcl_script", 
    "generate_mdp_file",
    "validate_python_code",
    "validate_tcl_code",
    "get_programmer_tools",
    "get_tool_metadata",
    "ProgrammerToolExecutor"
]

logger = logging.getLogger(__name__)


def get_programmer_tools() -> list:
    """
    Get all programmer @tool functions for LLM binding.
    
    Returns:
        List of StructuredTool objects ready for LLM use
    """
    return [
        generate_python_tool,
        generate_tcl_script,
        generate_mdp_file,
        validate_python_code,
        validate_tcl_code
    ]


def get_tool_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Extract metadata from all @tool functions.
    
    Returns:
        Dict mapping tool names to their metadata
    """
    tools = get_programmer_tools()
    metadata = {}
    
    for tool in tools:
        tool_info = {
            "name": tool.name,
            "description": tool.description,
            "args": {},
        }
        
        # Extract argument schema
        if hasattr(tool, 'args_schema') and tool.args_schema:
            schema = tool.args_schema.model_json_schema()
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


class ProgrammerToolExecutor:
    """
    Executes programmer tools in agent workflows.
    
    Provides unified interface for tool execution with:
    - Automatic working directory management
    - Result aggregation
    - Error handling
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.working_directory = self.config.get("working_directory", "programmer")
        self.tools = {tool.name: tool for tool in get_programmer_tools()}
        logger.info(f"ProgrammerToolExecutor initialized with {len(self.tools)} tools")
    
    def execute(self, generator_tool: str, **tool_params) -> Dict[str, Any]:
        """
        Execute a tool by name with parameters.
        
        Args:
            generator_tool: Name of the generator tool to execute (e.g., 'generate_python_tool')
            **tool_params: Parameters to pass to the generator tool
            
        Returns:
            Tool execution result
        """
        if generator_tool not in self.tools:
            return {
                "success": False,
                "error": f"Unknown tool: {generator_tool}"
            }
        
        try:
            # ALWAYS force working_dir to agent directory (prevent file leaks)
            tool_params["working_dir"] = self.working_directory
            
            # Execute tool using run() which accepts a dict of params
            # LangChain @tool decorated functions have a run() method
            tool = self.tools[generator_tool]
            result = tool.run(tool_params)  # Pass params as a dict
            
            logger.info(f"Generator tool {generator_tool} executed successfully")
            return result
            
        except Exception as e:
            logger.error(f"Generator tool execution failed for {generator_tool}: {e}", exc_info=True)
            return {
                "success": False,
                "tool": generator_tool,
                "error": str(e)
            }
