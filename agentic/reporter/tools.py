"""
Reporter Agent Tools
Thin wrapper that exposes modular @tool functions from src/reporter/
"""
import os
import logging
from typing import Dict, Any, List, Optional

# Import modular @tool functions from src/reporter/
from src.reporter.summary_reader import read_analysis_summary
from src.reporter.literature_search import search_pubmed, generate_literature_queries
from src.reporter.html_generator import generate_html_report

# Export tool functions for direct access
__all__ = [
    "ReporterToolExecutor",
    "read_analysis_summary",
    "search_pubmed",
    "generate_literature_queries",
    "generate_html_report",
    "get_reporter_tools",
    "get_tool_metadata",
]

logger = logging.getLogger(__name__)


def get_reporter_tools() -> list:
    """
    Get all reporter @tool functions for LLM binding.
    
    Returns:
        List of StructuredTool objects ready for LLM use
    """
    return [
        read_analysis_summary,
        search_pubmed,
        generate_literature_queries,
        generate_html_report,
    ]


def get_tool_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Dynamically extract metadata from all @tool functions.
    This replaces manual tool definitions in config.yaml
    
    Returns:
        Dict mapping tool names to their metadata
    """
    tools = get_reporter_tools()
    metadata = {}
    
    for tool in tools:
        tool_info = {
            "name": tool.name,
            "description": tool.description,
            "args": {},
        }
        
        # Extract argument schema from LangChain StructuredTool
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


class ReporterToolExecutor:
    """Executor for reporter tools"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.working_dir = config.get("working_directory", os.getcwd())
        logger.info(f"Reporter tool executor initialized (working_dir: {self.working_dir})")
    
    def execute_tool(self, tool_name: str, tool_params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a reporter tool by name"""
        
        # Map tool names to functions
        tools_map = {
            "read_analysis_summary": read_analysis_summary,
            "search_pubmed": search_pubmed,
            "generate_literature_queries": generate_literature_queries,
            "generate_html_report": generate_html_report
        }
        
        if tool_name not in tools_map:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(tools_map.keys())
            }
        
        try:
            # Add working_dir to params if not present
            if "working_dir" not in tool_params and "working_dir" in globals()[tool_name].func.__code__.co_varnames:
                tool_params["working_dir"] = self.working_dir
            
            # Execute tool
            tool_func = tools_map[tool_name]
            result = tool_func.invoke(tool_params)
            
            return result if isinstance(result, dict) else {"result": result}
            
        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "tool": tool_name
            }
