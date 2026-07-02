"""
Dynamic Tools Registry

Discovers and catalogs all tools across the project by introspecting tools.py files.
Extracts tool descriptions, parameters, and metadata from docstrings and decorators.
"""

import os
import re
import importlib.util
import inspect
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

from agentic.utils.tool_prompt_format import format_tool_for_llm_prompt

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
    
    def __init__(self, base_path: Optional[str] = None, working_directory: Optional[str] = None):
        """
        Initialize the tools registry.
        
        Args:
            base_path: Root directory to scan for tools (defaults to agentic/)
            working_directory: Runtime working directory (e.g. from state['working_directory']).
                Used to locate programmer-generated tools under {working_directory}/programmer/.
        """
        if base_path is None:
            # Default to agentic directory
            current_dir = Path(__file__).parent.parent
            base_path = str(current_dir)
        
        self.base_path = Path(base_path)
        self.working_directory = working_directory
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
        
        # CRITICAL: Clear existing tools to prevent duplication when refreshing
        self.tools.clear()
        self.tools_by_agent.clear()
        logger.debug("Cleared existing tools before rediscovery")
        
        # Agent directories to scan
        agent_dirs = [
            "supervisor",
            "preprocess",
            "simsetup",
            "hpc",
            "analysis",
            "reporter",
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
        
        # Also scan programmer-generated tools in working_dir
        self._scan_programmer_generated_tools()
        
        logger.info(f"Tool discovery complete. Found {len(self.tools)} tools across {len(self.tools_by_agent)} agents")
        return self.tools
    
    def _scan_programmer_generated_tools(self):
        """Scan {working_directory}/programmer for dynamically generated tools."""
        try:
            from agentic.utils import get_dynamic_tool_loader
            import os
            
            # Resolve programmer directory from working_directory
            if self.working_directory:
                programmer_dir = str(Path(self.working_directory) / "programmer")
            else:
                programmer_dir = "working_dir/programmer"
            
            if not os.path.exists(programmer_dir):
                logger.debug(f"Programmer directory does not exist: {programmer_dir}")
                return
            
            # Load programmer tools - MUST use refresh=True to reload from disk
            tool_loader = get_dynamic_tool_loader(programmer_dir=programmer_dir, refresh=True)
            programmer_tools = tool_loader.get_tools_for_agent("all")
            tool_metadata_list = tool_loader.get_tool_metadata_list()
            
            if not programmer_tools:
                logger.debug("No programmer-generated tools found")
                return
            
            logger.info(f"Discovered {len(programmer_tools)} programmer-generated tools")
            
            # Add to registry
            if "programmer_generated" not in self.tools_by_agent:
                self.tools_by_agent["programmer_generated"] = []
            
            for tool_metadata in tool_metadata_list:
                tool_name = tool_metadata["name"]
                self.tools[f"programmer.{tool_name}"] = tool_metadata
                self.tools_by_agent["programmer_generated"].append(tool_metadata)
                
                # CRITICAL: Also add programmer tools to the analysis agent category
                # so they appear when planner requests analysis tools
                if "analysis" not in self.tools_by_agent:
                    self.tools_by_agent["analysis"] = []
                self.tools_by_agent["analysis"].append(tool_metadata)
                
                logger.info(f"  Registered programmer tool: {tool_name} (available to analysis agent)")
                
        except Exception as e:
            logger.warning(f"Could not load programmer-generated tools: {e}")
    
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
                if self._is_tool_function(name, obj, module_name=module.__name__):
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
    
    def _is_tool_function(self, name: str, obj: Any, module_name: Optional[str] = None) -> bool:
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
            "get_hpc_tools",
            "get_reporter_tools",
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
        
        # Regular function with proper docstring. To avoid leaking imported helpers
        # (for example apply_pca_tool_defaults), only allow functions defined in
        # the scanned module.
        if (
            inspect.isfunction(obj)
            and obj.__doc__
            and len(obj.__doc__.strip()) > 20
            and (module_name is None or getattr(obj, "__module__", None) == module_name)
        ):
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
    
    @staticmethod
    def _dedupe_tools_by_name(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return tools deduplicated by tool name (first occurrence wins)."""
        seen: set[str] = set()
        deduped: List[Dict[str, Any]] = []
        for tool in tools:
            name = tool.get("name", "")
            if not name or name in seen:
                continue
            seen.add(name)
            deduped.append(tool)
        return deduped

    def get_tools_for_agent(
        self,
        agent_name: str,
        exclude_combined_tools: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Get all tools for a specific agent.
        
        Args:
            agent_name: Agent name (e.g., 'preprocess', 'setup')
            exclude_combined_tools: When True, omit cross-simulation combined-analysis
                tools from the analysis agent tool list.
            
        Returns:
            List of tool metadata dicts
        """
        tools = self._dedupe_tools_by_name(self.tools_by_agent.get(agent_name, []))
        if not exclude_combined_tools or agent_name != "analysis":
            return tools
        try:
            from agentic.analysis.tools import is_combined_analysis_tool
            return [t for t in tools if not is_combined_analysis_tool(t.get("name", ""))]
        except ImportError:
            return tools

    def _format_tools_compact(
        self,
        agent_name: str,
        tools: List[Dict[str, Any]],
        max_chars: int = 6000,
    ) -> str:
        """Compact tool listing for master-plan prompts (names + short descriptions)."""
        agent_descriptions = {
            "preprocess": "PDB cleanup, validation, hydrogen addition",
            "simsetup": "Topology, solvation, ions, MDP/TPR generation",
            "hpc": "SLURM submission and job monitoring",
            "analysis": "Per-simulation trajectory metrics and plots",
            "reporter": "HTML reports, literature search, summaries",
        }
        header = f"**{agent_name.upper()} AGENT:**"
        expertise = agent_descriptions.get(agent_name.lower(), "")
        lines = [header]
        if expertise:
            lines.append(f"Role: {expertise}")
        for tool in tools:
            params = tool.get("parameters") or {}
            param_names = ", ".join(params.keys()) if params else "—"
            desc = (tool.get("description") or "").strip().split("\n")[0]
            if len(desc) > 120:
                desc = desc[:117] + "..."
            lines.append(f"  • {tool['name']}({param_names}): {desc}")
        text = "\n".join(lines)
        if len(text) <= max_chars:
            return text
        truncated = text[: max_chars - 40].rsplit("\n", 1)[0]
        return truncated + f"\n  … ({len(tools)} tools total; list truncated)"

    @staticmethod
    def _annotate_args_required_optional(
        description: str,
        parameters: Dict[str, Dict[str, Any]],
    ) -> str:
        """Inline required/optional flags into Args lines when possible."""
        if not description or not parameters or "Args:" not in description:
            return description

        lines = description.split("\n")
        in_args = False
        out: List[str] = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("Args:"):
                in_args = True
                out.append(line)
                continue
            if in_args and (stripped.startswith("Returns:") or stripped.startswith("Raises:")):
                in_args = False
                out.append(line)
                continue

            if in_args:
                match = re.match(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
                if match:
                    indent, arg_name, rest = match.groups()
                    if arg_name in parameters:
                        req = "required" if parameters[arg_name].get("required") else "optional"
                        out.append(f"{indent}{arg_name} ({req}): {rest}")
                        continue

            out.append(line)

        return "\n".join(out)

    def get_combined_only_tools_context(self, max_chars: int = 5000) -> str:
        """Tools that run once at project base across multiple simulations."""
        try:
            from agentic.analysis.tools import COMBINED_ANALYSIS_TOOL_NAMES
        except ImportError:
            return "(No cross-simulation combined tools registered.)"

        combined_tools = [
            t
            for t in self.get_tools_for_agent("analysis", exclude_combined_tools=False)
            if t.get("name") in COMBINED_ANALYSIS_TOOL_NAMES
        ]
        if not combined_tools:
            return "(No cross-simulation combined tools registered.)"
        return self._format_tools_compact(
            "analysis (cross-simulation only)",
            combined_tools,
            max_chars=max_chars,
        )

    def get_master_plan_per_sim_tools_context(
        self,
        agent_list: List[str],
        max_chars_per_agent: int = 5500,
    ) -> str:
        """
        Per-simulation tools for each workflow agent in *agent_list*.

        Uses compact formatting and a per-agent char budget so large analysis
        tool lists do not crowd out reporter (or other) agents.
        """
        _cli_to_registry = {
            "preprocess": "preprocess",
            "simsetup": "simsetup",
            "hpcjob": "hpc",
            "analysis": "analysis",
            "reporter": "reporter",
        }
        parts: List[str] = []
        seen: set[str] = set()
        for cli_name in agent_list:
            registry_name = _cli_to_registry.get(cli_name, cli_name)
            if registry_name in seen:
                continue
            seen.add(registry_name)
            exclude_combined = registry_name == "analysis"
            tools = self.get_tools_for_agent(
                registry_name,
                exclude_combined_tools=exclude_combined,
            )
            if not tools:
                logger.warning(
                    "ToolsRegistry: no per-sim tools for agent '%s'", registry_name
                )
                continue
            parts.append(
                self._format_tools_compact(
                    registry_name,
                    tools,
                    max_chars=max_chars_per_agent,
                )
            )
        return "\n\n".join(parts) if parts else "(No per-simulation tools found.)"
    
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
    
    def get_tools_for_planner(
        self,
        agent_name: Optional[str] = None,
        exclude_combined_tools: bool = False,
    ) -> str:
        """
        Get formatted tools description for planner LLM context.
        
        Args:
            agent_name: If specified, only return tools for this agent
            exclude_combined_tools: When True, omit cross-simulation combined-analysis
                tools from the analysis agent section.
            
        Returns:
            Formatted string suitable for LLM prompts
        """
        if agent_name:
            tools = self.get_tools_for_agent(
                agent_name,
                exclude_combined_tools=exclude_combined_tools,
            )
            agents_to_format = {agent_name: tools}
        else:
            agents_to_format = {
                agent: self.get_tools_for_agent(
                    agent,
                    exclude_combined_tools=exclude_combined_tools,
                )
                for agent in self.tools_by_agent
            }
        
        # Agent descriptions for planner context
        agent_descriptions = {
            "preprocess": "Handles PDB structure cleanup, validation, and preparation. Expertise: removing waters/ligands, fixing residues, adding hydrogens, validating structure integrity.",
            "simsetup": "Handles MD simulation system setup. Expertise: topology generation, force field application, solvation, ion addition, MDP parameter file creation, ligand parameterization.",
            "hpc": "Handles job submission and execution on HPC clusters. Expertise: creating SLURM scripts, submitting jobs, monitoring execution, retrieving results from compute nodes.",
            "analysis": "Handles MD trajectory analysis and visualization. Expertise: calculating RMSD/RMSF, structural analysis (secondary structure, hydrogen bonds), energy analysis, creating plots.",
            "reporter": "Handles scientific report generation from completed analysis results. Expertise: summarizing analysis outputs, creating HTML/markdown reports, embedding plots and tables, formatting scientific documents.",
            "programmer": "Generates custom Python/TCL/MDP tools based on specifications. Expertise: creating analysis scripts, MD parameter generators, visualization tools, data processing functions."
        }
        
        # Use workflow order instead of alphabetical
        workflow_order = ["preprocess", "simsetup", "hpc", "analysis", "reporter", "supervisor"]
        
        formatted = []
        
        # Sort agents by workflow order
        def agent_sort_key(agent_name):
            for i, workflow_agent in enumerate(workflow_order):
                if workflow_agent in agent_name.lower():
                    return i
            return 999  # Unknown agents go last
        
        sorted_agents = sorted(agents_to_format.items(), key=lambda x: agent_sort_key(x[0]))
        
        for agent, tools in sorted_agents:
            formatted.append(f"\n**{agent.upper()} Agent Tools:**")
            
            # Add agent expertise description
            agent_key = agent.lower()
            if agent_key in agent_descriptions:
                formatted.append(f"Agent Expertise: {agent_descriptions[agent_key]}")
                formatted.append("")  # Blank line
            
            for tool in tools:
                formatted.append(
                    format_tool_for_llm_prompt(
                        tool["name"],
                        tool.get("description", ""),
                        tool.get("parameters") or {},
                    )
                )
        
        return "\n".join(formatted)


# Global registry instance
_global_registry = None


def get_tools_registry(base_path: Optional[str] = None, refresh: bool = False,
                       working_directory: Optional[str] = None) -> ToolsRegistry:
    """
    Get or create the global tools registry.
    
    Args:
        base_path: Root directory to scan (optional)
        refresh: If True, rediscover all tools
        working_directory: Runtime working directory for resolving programmer tools
        
    Returns:
        ToolsRegistry instance
    """
    global _global_registry
    
    if _global_registry is None or refresh:
        _global_registry = ToolsRegistry(base_path, working_directory=working_directory)
        _global_registry.discover_all_tools()
    
    return _global_registry
