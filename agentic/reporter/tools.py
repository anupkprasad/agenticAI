"""
Reporter Agent Tools
Thin wrapper that exposes modular @tool functions from src/reporter/
"""
import os
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import modular @tool functions from src/reporter/
from src.reporter.summary_reader import read_analysis_summary
from src.reporter.literature_search import (
    search_pubmed, generate_literature_queries,
    search_biorxiv, search_uniprot,
)
from src.reporter.html_generator import generate_html_report
from src.reporter.combined_reporter import generate_combined_html_report

# Export tool functions for direct access
__all__ = [
    "ReporterToolExecutor",
    "read_analysis_summary",
    "search_pubmed",
    "search_biorxiv",
    "search_uniprot",
    "generate_literature_queries",
    "generate_html_report",
    "generate_combined_html_report",
    "get_reporter_tools",
    "get_tool_metadata",
]

logger = logging.getLogger(__name__)


def get_reporter_tools(include_combined: bool = True, include_shared: bool = True) -> list:
    """
    Get reporter @tool functions for LLM binding.

    Args:
        include_combined: Include combined HTML report tool.
        include_shared: Include literature search tools (usable in both modes).
    """
    from agentic.reporter.tool_buckets import (
        COMBINED_TOOL_NAMES,
        PER_SIM_TOOL_NAMES,
        SHARED_TOOL_NAMES,
    )

    all_tools = [
        read_analysis_summary,
        search_pubmed,
        search_biorxiv,
        search_uniprot,
        generate_literature_queries,
        generate_html_report,
        generate_combined_html_report,
    ]
    allowed = set(PER_SIM_TOOL_NAMES)
    if include_combined:
        allowed |= set(COMBINED_TOOL_NAMES)
    if include_shared:
        allowed |= set(SHARED_TOOL_NAMES)
    return [t for t in all_tools if getattr(t, "name", "") in allowed]


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
            "search_biorxiv": search_biorxiv,
            "search_uniprot": search_uniprot,
            "generate_literature_queries": generate_literature_queries,
            "generate_html_report": generate_html_report,
            "generate_combined_html_report": generate_combined_html_report,
        }
        
        if tool_name not in tools_map:
            try:
                from agentic.utils.sandbox_files import execute_sandbox_tool

                wd = Path(self.working_dir)
                sand = execute_sandbox_tool(
                    tool_name,
                    tool_params,
                    roots=[wd.parent, wd],
                    sim_root=str(wd.parent),
                )
                if sand is not None:
                    return sand
            except Exception:
                pass
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}",
                "available_tools": list(tools_map.keys())
            }
        
        try:
            # Only force working_dir to the agent directory for output tools
            # (e.g. generate_html_report).  Input tools like read_analysis_summary
            # need to read from the parent working directory and must keep whatever
            # working_dir the caller has already set in tool_params.
            _OUTPUT_TOOLS = {"generate_html_report", "generate_combined_html_report"}
            if tool_name in _OUTPUT_TOOLS:
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
