"""
Dynamic Tools Registry

Discovers and catalogs all tools across the project by introspecting tools.py files.
Extracts tool descriptions, parameters, and metadata from docstrings and decorators.
"""

import os
import importlib.util
import inspect
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ToolsRegistry:
    """
    Dynamically discovers and registers all tools from the project.
    
    Scans all agent directories for tools.py files and extracts:
    - Tool function names
    - Descriptions from docstrings
    - Parameter specifications
    - Agent context
    """
    
    def __init__(self, base_path: Optional[str] = None):
        """
        Initialize the tools registry.
        
        Args:
            base_path: Root directory to scan for tools (defaults to agentic/)
        """
        if base_path is None:
            # Default to agentic directory
            current_dir = Path(__file__).parent.parent
            base_path = str(current_dir)
        
        self.base_path = Path(base_path)
        self.tools = {}
        self.tools_by_agent = {}
        
        logger.info(f"Initializing ToolsRegistry with base_path: {self.base_path}")
    
    def discover_all_tools(self) -> Dict[str, Any]:
        """
        Discover all tools across the project.
        
        Returns:
            Dict mapping tool names to their metadata
        """
        logger.info("Starting tool discovery...")
        
        # Agent directories to scan
        agent_dirs = [
            "supervisor",
            "preprocess",
            "simsetup",
            "hpc",
            "analysis",
            "planner",
            "programmer"
        ]
        
        for agent_name in agent_dirs:
            agent_path = self.base_path / agent_name
            if not agent_path.exists():
                logger.debug(f"Agent directory not found: {agent_path}")
                continue
            
            # Look for tools.py in agent directory
            tools_file = agent_path / "tools.py"
            if tools_file.exists():
                self._scan_tools_file(str(tools_file), agent_name)
        
        logger.info(f"Tool discovery complete. Found {len(self.tools)} tools across {len(self.tools_by_agent)} agents")
        return self.tools
    
    def _scan_tools_file(self, file_path: str, agent_name: str):
        """
        Scan a tools.py file and extract tool definitions.
        
        Args:
            file_path: Path to tools.py file
            agent_name: Name of the agent owning these tools
        """
        logger.debug(f"Scanning tools file: {file_path} for agent: {agent_name}")
        
        try:
            # Load module dynamically
            spec = importlib.util.spec_from_file_location(f"{agent_name}_tools", file_path)
            if spec is None or spec.loader is None:
                logger.warning(f"Could not load spec for {file_path}")
                return
            
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # Extract tools from module
            tools_found = 0
            for name, obj in inspect.getmembers(module):
                if self._is_tool_function(name, obj):
                    tool_info = self._extract_tool_info(name, obj, agent_name)
                    self.tools[f"{agent_name}.{name}"] = tool_info
                    
                    # Group by agent
                    if agent_name not in self.tools_by_agent:
                        self.tools_by_agent[agent_name] = []
                    self.tools_by_agent[agent_name].append(tool_info)
                    
                    tools_found += 1
            
            logger.info(f"Found {tools_found} tools in {agent_name}/tools.py")
            
        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}", exc_info=True)
    
    def _is_tool_function(self, name: str, obj: Any) -> bool:
        """
        Determine if an object is a tool function (including LangChain @tool decorated).
        
        Args:
            name: Object name
            obj: Python object
            
        Returns:
            True if this is a tool function
        """
        # Skip private functions
        if name.startswith("_"):
            return False
        
        # CRITICAL: Skip meta-functions that return tool lists/metadata
        # These are internal utilities, not operational tools
        meta_function_names = {
            "get_preprocessing_tools",
            "get_simulation_setup_tools",
            "get_tool_metadata",
            "get_analysis_tools",
            "get_hpc_tools"
        }
        if name in meta_function_names:
            return False
        
        # Skip imported modules and classes
        if inspect.ismodule(obj) or inspect.isclass(obj):
            return False
        
        # Check for LangChain StructuredTool (from @tool decorator) - PRIORITY CHECK
        # Note: StructuredTool is NOT callable() but has these attributes
        if hasattr(obj, 'name') and hasattr(obj, 'description') and hasattr(obj, 'args_schema'):
            return True
        
        # Check if it's callable (regular functions)
        if not callable(obj):
            return False
        
        # Check if it's a decorated function with __wrapped__
        if hasattr(obj, "__wrapped__"):
            return True
        
        # Regular function with proper docstring
        if inspect.isfunction(obj) and obj.__doc__ and len(obj.__doc__.strip()) > 20:
            return True
        
        return False
    
    def _extract_tool_info(self, name: str, func: callable, agent_name: str) -> Dict[str, Any]:
        """
        Extract metadata from a tool function (including LangChain StructuredTool).
        
        Args:
            name: Function name
            func: Function object or StructuredTool instance
            agent_name: Agent owning this tool
            
        Returns:
            Dict with tool metadata
        """
        # Handle LangChain StructuredTool (from @tool decorator)
        if hasattr(func, 'name') and hasattr(func, 'description') and hasattr(func, 'args_schema'):
            # This is a LangChain StructuredTool
            tool_name = func.name
            description = func.description or "No description available"
            
            # Extract parameters from args_schema (Pydantic model)
            parameters = {}
            if hasattr(func, 'args_schema') and func.args_schema:
                schema = func.args_schema
                if hasattr(schema, 'schema'):
                    schema_dict = schema.schema()
                    properties = schema_dict.get('properties', {})
                    required_fields = schema_dict.get('required', [])
                    
                    for param_name, param_def in properties.items():
                        parameters[param_name] = {
                            "required": param_name in required_fields,
                            "type": param_def.get('type', 'Any'),
                            "description": param_def.get('description', 'No description'),
                            "default": param_def.get('default', None)
                        }
            
            return {
                "name": tool_name,
                "full_name": f"{agent_name}.{tool_name}",
                "agent": agent_name,
                "description": description,
                "parameters": parameters,
                "docstring": description,
                "tool_type": "langchain_structured_tool"
            }
        
        # Handle regular functions
        # Extract docstring
        doc = inspect.getdoc(func) or "No description available"
        
        # Parse docstring to separate description and args
        description, args_doc = self._parse_docstring(doc)
        
        # Get function signature
        sig = inspect.signature(func)
        parameters = {}
        
        for param_name, param in sig.parameters.items():
            param_info = {
                "required": param.default == inspect.Parameter.empty,
                "default": None if param.default == inspect.Parameter.empty else param.default,
                "type": str(param.annotation) if param.annotation != inspect.Parameter.empty else "Any"
            }
            
            # Try to get description from docstring
            if param_name in args_doc:
                param_info["description"] = args_doc[param_name]
            
            parameters[param_name] = param_info
        
        return {
            "name": name,
            "full_name": f"{agent_name}.{name}",
            "agent": agent_name,
            "description": description,
            "parameters": parameters,
            "docstring": doc,
            "tool_type": "python_function"
        }
    
    def _parse_docstring(self, docstring: str) -> tuple[str, Dict[str, str]]:
        """
        Parse docstring to extract description and parameter docs.
        
        Args:
            docstring: Function docstring
            
        Returns:
            Tuple of (description, parameter_docs_dict)
        """
        lines = docstring.strip().split("\n")
        
        # Find the main description (everything before Args:)
        description_lines = []
        args_section = []
        in_args = False
        
        for line in lines:
            if line.strip().startswith("Args:"):
                in_args = True
                continue
            elif line.strip().startswith("Returns:") or line.strip().startswith("Raises:"):
                in_args = False
                continue
            
            if in_args:
                args_section.append(line)
            elif not in_args:
                description_lines.append(line)
        
        description = "\n".join(description_lines).strip()
        
        # Parse arguments
        args_dict = {}
        for line in args_section:
            line = line.strip()
            if ":" in line and not line.startswith(" "):
                parts = line.split(":", 1)
                if len(parts) == 2:
                    arg_name = parts[0].strip()
                    arg_desc = parts[1].strip()
                    args_dict[arg_name] = arg_desc
        
        return description, args_dict
    
    def get_tools_for_agent(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get all tools for a specific agent.
        
        Args:
            agent_name: Agent name (e.g., 'preprocess', 'setup')
            
        Returns:
            List of tool metadata dicts
        """
        return self.tools_by_agent.get(agent_name, [])
    
    def get_all_tools_summary(self) -> str:
        """
        Generate a human-readable summary of all available tools.
        
        Returns:
            Formatted string with tools organized by agent
        """
        summary = ["=" * 80, "AVAILABLE TOOLS ACROSS ALL AGENTS", "=" * 80, ""]
        
        for agent_name, tools in sorted(self.tools_by_agent.items()):
            summary.append(f"\n### {agent_name.upper()} AGENT TOOLS ###")
            summary.append("-" * 60)
            
            for tool in tools:
                summary.append(f"\n🔧 {tool['name']}")
                summary.append(f"   Description: {tool['description'][:200]}...")
                
                if tool['parameters']:
                    summary.append("   Parameters:")
                    for param_name, param_info in tool['parameters'].items():
                        required = "required" if param_info['required'] else "optional"
                        summary.append(f"      - {param_name} ({required}): {param_info.get('description', 'N/A')}")
                
                summary.append("")
        
        summary.append("=" * 80)
        return "\n".join(summary)
    
    def get_tools_for_planner(self, agent_name: Optional[str] = None) -> str:
        """
        Get formatted tools description for planner LLM context.
        
        Args:
            agent_name: If specified, only return tools for this agent
            
        Returns:
            Formatted string suitable for LLM prompts
        """
        if agent_name:
            tools = self.get_tools_for_agent(agent_name)
            agents_to_format = {agent_name: tools}
        else:
            agents_to_format = self.tools_by_agent
        
        formatted = []
        
        for agent, tools in sorted(agents_to_format.items()):
            formatted.append(f"\n**{agent.upper()} Agent Tools:**")
            
            for tool in tools:
                formatted.append(f"\n- **{tool['name']}**")
                formatted.append(f"  {tool['description']}")
                
                if tool['parameters']:
                    formatted.append("  Parameters:")
                    for param_name, param_info in tool['parameters'].items():
                        req_str = "required" if param_info['required'] else "optional"
                        desc = param_info.get('description', 'No description')
                        formatted.append(f"    • {param_name} ({req_str}): {desc}")
        
        return "\n".join(formatted)


# Global registry instance
_global_registry = None


def get_tools_registry(base_path: Optional[str] = None, refresh: bool = False) -> ToolsRegistry:
    """
    Get or create the global tools registry.
    
    Args:
        base_path: Root directory to scan (optional)
        refresh: If True, rediscover all tools
        
    Returns:
        ToolsRegistry instance
    """
    global _global_registry
    
    if _global_registry is None or refresh:
        _global_registry = ToolsRegistry(base_path)
        _global_registry.discover_all_tools()
    
    return _global_registry
