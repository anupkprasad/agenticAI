"""
Programmer Agent Tools - Code Generation Tools

Provides @tool functions for generating custom Python and TCL tools
that can be used by field agents during workflow execution.

Invoked by planner when existing tools are insufficient for the workflow.
"""
import os
import ast
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from langchain.tools import tool

logger = logging.getLogger(__name__)


def _extract_imports_from_code(code: str) -> tuple[set[str], str]:
    """
    Extract import statements from code and return them separately.
    
    Args:
        code: Python code that may contain import statements
        
    Returns:
        Tuple of (set of import lines, code without imports)
    """
    lines = code.split("\n")
    import_lines = set()
    non_import_lines = []
    
    for line in lines:
        stripped = line.strip()
        # Check if line is an import statement
        if stripped.startswith("import ") or stripped.startswith("from "):
            import_lines.add(stripped)
        elif stripped == "":
            # Keep blank lines in non-import section
            non_import_lines.append(line)
        else:
            # Regular code line
            non_import_lines.append(line)
    
    return import_lines, "\n".join(non_import_lines)


# Export all tools
__all__ = [
    "generate_python_tool",
    "generate_tcl_script", 
    "generate_mdp_file",
    "generate_analysis_script",
    "validate_python_code",
    "validate_tcl_code",
    "get_programmer_tools",
    "get_tool_metadata",
    "ProgrammerToolExecutor"
]


@tool
def generate_python_tool(
    tool_name: str,
    description: str,
    parameters: Dict[str, Dict[str, Any]],
    implementation: str,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    add_langchain_decorator: bool = True
) -> Dict[str, Any]:
    """
    Generate a Python tool with proper structure and decorators.
    
    Creates a complete Python function with:
    - Type hints and docstring
    - LangChain @tool decorator (optional)
    - Error handling and logging
    - Parameter validation
    
    Args:
        tool_name: Name of the tool/function
        description: What the tool does
        parameters: Parameter specs {param_name: {type, description, default}}
        implementation: Core logic as Python code
        output_file: Output file path (default: working_dir/python/{tool_name}.py)
        working_dir: Working directory (default: working_dir/programmer)
        add_langchain_decorator: Add @tool decorator for LangChain
        
    Returns:
        Dict with generation results
    """
    try:
        # Set default paths
        if not working_dir:
            working_dir = "working_dir/programmer"
        
        # Save directly to working_dir/programmer/, not subdirectory
        os.makedirs(working_dir, exist_ok=True)
        
        if not output_file:
            output_file = os.path.join(working_dir, f"{tool_name}.py")
        
        # Build function code
        code_parts = []
        
        # Extract imports from implementation code to avoid duplication
        impl_imports, cleaned_implementation = _extract_imports_from_code(implementation)
        
        # Module-level imports (ensure no duplicates)
        base_imports = {
            "import os",
            "import logging",
            "from typing import Dict, Any, Optional, List",
            "from pathlib import Path"
        }
        
        # Add LangChain import if needed
        if add_langchain_decorator:
            base_imports.add("from langchain.tools import tool")
        
        # Merge with implementation imports
        all_imports = base_imports | impl_imports
        
        # Docstring header
        code_parts.append('"""')
        code_parts.append(f"Generated tool: {tool_name}")
        code_parts.append("")
        code_parts.append(description)
        code_parts.append("")
        code_parts.append("⚠️ IMPORTANT: If this is an analysis tool, it MUST log results to analysis_summary.jsonl")
        code_parts.append("using append_analysis_summary() with statistics (min/max/mean/std) and metadata.")
        code_parts.append("This enables LLMs to answer questions about analysis results.")
        code_parts.append('"""')
        
        # Add all imports (sorted for consistency)
        for imp in sorted(all_imports):
            code_parts.append(imp)
        
        code_parts.append("")
        code_parts.append("logger = logging.getLogger(__name__)")
        code_parts.append("")
        
        # Add path resolution helper function for cross-directory file access
        code_parts.append('# Path resolution helper for cross-directory file access')
        code_parts.append('def _resolve_input_path(file_ref: str, param_name: str = "input") -> Path:')
        code_parts.append('    """Resolve file reference to absolute path with validation."""')
        code_parts.append('    file_path = Path(file_ref)')
        code_parts.append('    ')
        code_parts.append('    # If already absolute and exists, return it')
        code_parts.append('    if file_path.is_absolute():')
        code_parts.append('        if file_path.exists():')
        code_parts.append('            return file_path')
        code_parts.append('        else:')
        code_parts.append('            raise FileNotFoundError(f"{param_name} file not found: {file_ref}")')
        code_parts.append('    ')
        code_parts.append('    # Try as relative to current directory')
        code_parts.append('    if file_path.exists():')
        code_parts.append('        return file_path.resolve()')
        code_parts.append('    ')
        code_parts.append('    # Try resolving from cwd')
        code_parts.append('    cwd_path = Path.cwd() / file_ref')
        code_parts.append('    if cwd_path.exists():')
        code_parts.append('        return cwd_path')
        code_parts.append('    ')
        code_parts.append('    # Try just resolving (may expand relative paths)')
        code_parts.append('    resolved = file_path.resolve()')
        code_parts.append('    if resolved.exists():')
        code_parts.append('        return resolved')
        code_parts.append('    ')
        code_parts.append('    raise FileNotFoundError(')
        code_parts.append('        f"{param_name} file not found: {file_ref} "')
        code_parts.append('        f"(tried: {file_path}, {cwd_path}, {resolved})"')
        code_parts.append('    )')
        code_parts.append("")
        code_parts.append("# ⚠️ IMPORTANT: Use _resolve_input_path() for INPUT files ONLY (trajectory, topology)")
        code_parts.append("# For OUTPUT files, use the filename directly - you're already in working_dir!")
        code_parts.append("")
        
        # Function definition
        if add_langchain_decorator:
            code_parts.append("@tool")
        
        # Build parameter list
        param_list = []
        for param_name, param_spec in parameters.items():
            param_type = param_spec.get("type", "Any")
            if "default" in param_spec:
                param_list.append(f"{param_name}: {param_type} = {repr(param_spec['default'])}")
            else:
                param_list.append(f"{param_name}: {param_type}")
        
        # Always add working_dir parameter at the end
        param_list.append("working_dir: Optional[str] = None")
        
        params_str = ", ".join(param_list)
        code_parts.append(f"def {tool_name}({params_str}) -> Dict[str, Any]:")
        
        # Docstring
        code_parts.append('    """')
        code_parts.append(f"    {description}")
        code_parts.append("    ")
        code_parts.append("    Args:")
        for param_name, param_spec in parameters.items():
            param_desc = param_spec.get("description", "No description")
            code_parts.append(f"        {param_name}: {param_desc}")
        code_parts.append("        working_dir: Working directory for analysis (optional)")
        code_parts.append("    ")
        code_parts.append("    Returns:")
        code_parts.append("        Dict with execution results")
        code_parts.append('    """')
        
        # Implementation
        code_parts.append("    try:")
        # Add working directory setup
        code_parts.append("        # Setup working directory if provided")
        code_parts.append("        original_dir = None")
        code_parts.append("        if working_dir:")
        code_parts.append("            os.makedirs(working_dir, exist_ok=True)")
        code_parts.append("            original_dir = os.getcwd()")
        code_parts.append("            os.chdir(working_dir)")
        code_parts.append("        ")
        code_parts.append("        # Implementation logic (imports extracted to module level)")
        # Indent cleaned implementation (without import statements)
        for line in cleaned_implementation.split("\n"):
            if line.strip():  # Skip empty lines at the start
                code_parts.append("        " + line)  # Don't use f-string - breaks if line contains {}
            elif code_parts[-1].strip():  # Keep blank lines between code blocks
                code_parts.append("        ")
        code_parts.append("")
        code_parts.append("        # Restore original directory if changed")
        code_parts.append("        if original_dir:")
        code_parts.append("            os.chdir(original_dir)")
        code_parts.append("        ")
        code_parts.append("        return {")
        code_parts.append('            "success": True,')
        code_parts.append(f'            "tool": "{tool_name}",')
        code_parts.append('            "message": "Tool execution completed"')
        code_parts.append("        }")
        code_parts.append("    except Exception as e:")
        code_parts.append("        # Restore original directory on error")
        code_parts.append("        if 'original_dir' in locals() and original_dir:")
        code_parts.append("            os.chdir(original_dir)")
        code_parts.append(f'        logger.error("Tool {tool_name} failed: " + str(e))')
        code_parts.append("        return {")
        code_parts.append('            "success": False,')
        code_parts.append(f'            "tool": "{tool_name}",')
        code_parts.append('            "error": str(e)')
        code_parts.append("        }")
        
        code = "\n".join(code_parts)
        
        # Validate syntax
        try:
            ast.parse(code)
            syntax_valid = True
        except SyntaxError as e:
            syntax_valid = False
            logger.error(f"Generated code has syntax error: {e}")
        
        # Write to file
        with open(output_file, "w") as f:
            f.write(code)
        
        return {
            "success": True,
            "tool_name": tool_name,
            "file_path": output_file,
            "language": "python",
            "syntax_valid": syntax_valid,
            "has_decorator": add_langchain_decorator,
            "message": f"Generated Python tool: {tool_name}"
        }
        
    except Exception as e:
        logger.error(f"Failed to generate Python tool {tool_name}: {e}")
        return {
            "success": False,
            "tool_name": tool_name,
            "error": str(e)
        }


@tool
def generate_tcl_script(
    script_name: str,
    description: str,
    parameters: Dict[str, Dict[str, Any]],
    implementation: str,
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None,
    target_program: str = "vmd"
) -> Dict[str, Any]:
    """
    Generate a TCL script for VMD/NAMD analysis.
    
    Creates a complete TCL script with:
    - Header comments and usage
    - Parameter handling
    - Error checking
    - Progress reporting
    
    Args:
        script_name: Name of the script
        description: What the script does
        parameters: Parameter specs {param_name: {type, description, default}}
        implementation: Core logic as TCL code
        output_file: Output file path (default: working_dir/tcl/{script_name}.tcl)
        working_dir: Working directory (default: working_dir/programmer)
        target_program: Target program (vmd, namd, etc.)
        
    Returns:
        Dict with generation results
    """
    try:
        # Set default paths
        if not working_dir:
            working_dir = "working_dir/programmer"
        
        tcl_dir = os.path.join(working_dir, "tcl")
        os.makedirs(tcl_dir, exist_ok=True)
        
        if not output_file:
            output_file = os.path.join(tcl_dir, f"{script_name}.tcl")
        
        # Build TCL script
        code_parts = []
        
        # Header
        code_parts.append("#!/usr/bin/env tclsh")
        code_parts.append("#")
        code_parts.append(f"# {script_name}.tcl")
        code_parts.append(f"# {description}")
        code_parts.append("#")
        code_parts.append(f"# Target: {target_program}")
        code_parts.append("#")
        code_parts.append("# Usage:")
        param_usage = " ".join([f"{{{p}}}" for p in parameters.keys()])
        code_parts.append(f"#   {target_program} -dispdev text -e {script_name}.tcl -args {param_usage}")
        code_parts.append("")
        
        # Parameter handling
        code_parts.append("# Parse command-line arguments")
        for idx, (param_name, param_spec) in enumerate(parameters.items()):
            default = param_spec.get("default", '""')
            code_parts.append(f"if {{[llength $argv] > {idx}}} {{")
            code_parts.append(f"    set {param_name} [lindex $argv {idx}]")
            code_parts.append("} else {")
            code_parts.append(f"    set {param_name} {default}")
            code_parts.append("}")
        code_parts.append("")
        
        # Implementation
        code_parts.append("# Main implementation")
        code_parts.append(implementation)
        code_parts.append("")
        
        # Footer
        code_parts.append("# Script completed")
        code_parts.append(f'puts "Script {script_name} completed successfully"')
        
        if target_program == "vmd":
            code_parts.append("quit")
        
        code = "\n".join(code_parts)
        
        # Write to file
        with open(output_file, "w") as f:
            f.write(code)
        
        # Make executable
        os.chmod(output_file, 0o755)
        
        return {
            "success": True,
            "script_name": script_name,
            "file_path": output_file,
            "language": "tcl",
            "target_program": target_program,
            "message": f"Generated TCL script: {script_name}"
        }
        
    except Exception as e:
        logger.error(f"Failed to generate TCL script {script_name}: {e}")
        return {
            "success": False,
            "script_name": script_name,
            "error": str(e)
        }


@tool
def generate_mdp_file(
    mdp_type: str,
    parameters: Dict[str, Any],
    force_field: str = "amber99sb-ildn",
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate GROMACS MDP (parameter) file.
    
    Creates MDP files for different simulation stages:
    - minimization: Energy minimization
    - nvt: NVT equilibration (constant N, V, T)
    - npt: NPT equilibration (constant N, P, T)
    - md: Production MD run
    
    Args:
        mdp_type: Type of MDP file (minimization, nvt, npt, md)
        parameters: MDP parameters {param_name: value}
        force_field: Force field being used
        output_file: Output file path (default: working_dir/mdp/{mdp_type}.mdp)
        working_dir: Working directory (default: working_dir/programmer)
        
    Returns:
        Dict with generation results
    """
    try:
        # Set default paths
        if not working_dir:
            working_dir = "working_dir/programmer"
        
        mdp_dir = os.path.join(working_dir, "mdp")
        os.makedirs(mdp_dir, exist_ok=True)
        
        if not output_file:
            output_file = os.path.join(mdp_dir, f"{mdp_type}.mdp")
        
        # Build MDP content
        lines = []
        lines.append(f"; MDP file for {mdp_type}")
        lines.append(f"; Force field: {force_field}")
        lines.append("; Generated by Programmer Agent")
        lines.append("")
        
        # Add parameters
        for key, value in parameters.items():
            if isinstance(value, dict) and "comment" in value:
                lines.append(f"; {value['comment']}")
                lines.append(f"{key} = {value['value']}")
            else:
                lines.append(f"{key} = {value}")
            lines.append("")
        
        content = "\n".join(lines)
        
        # Write to file
        with open(output_file, "w") as f:
            f.write(content)
        
        return {
            "success": True,
            "mdp_type": mdp_type,
            "file_path": output_file,
            "force_field": force_field,
            "message": f"Generated MDP file: {mdp_type}.mdp"
        }
        
    except Exception as e:
        logger.error(f"Failed to generate MDP file {mdp_type}: {e}")
        return {
            "success": False,
            "mdp_type": mdp_type,
            "error": str(e)
        }


@tool
def generate_analysis_script(
    script_name: str,
    description: str,
    analysis_type: str,
    input_files: List[str],
    output_file: Optional[str] = None,
    working_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate Python analysis script for MD trajectories.
    
    Creates standalone analysis scripts using MDAnalysis.
    
    Args:
        script_name: Name of the script
        description: What the analysis does
        analysis_type: Type (rmsd, rmsf, distance, angle, etc.)
        input_files: Required input files (topology, trajectory, etc.)
        output_file: Output file path (default: working_dir/analysis/{script_name}.py)
        working_dir: Working directory (default: working_dir/programmer)
        
    Returns:
        Dict with generation results
    """
    try:
        # Set default paths
        if not working_dir:
            working_dir = "working_dir/programmer"
        
        analysis_dir = os.path.join(working_dir, "analysis")
        os.makedirs(analysis_dir, exist_ok=True)
        
        if not output_file:
            output_file = os.path.join(analysis_dir, f"{script_name}.py")
        
        # Build script
        code_parts = []
        code_parts.append("#!/usr/bin/env python3")
        code_parts.append('"""')
        code_parts.append(f"{script_name}")
        code_parts.append("")
        code_parts.append(description)
        code_parts.append('"""')
        code_parts.append("import MDAnalysis as mda")
        code_parts.append("import numpy as np")
        code_parts.append("import matplotlib.pyplot as plt")
        code_parts.append("")
        code_parts.append("def main():")
        code_parts.append(f'    """Main {analysis_type} analysis"""')
        code_parts.append("    # Load trajectory")
        code_parts.append(f"    # Required inputs: {', '.join(input_files)}")
        code_parts.append("    ")
        code_parts.append(f"    print('Running {analysis_type} analysis...')")
        code_parts.append("    # Analysis implementation goes here")
        code_parts.append("    ")
        code_parts.append("if __name__ == '__main__':")
        code_parts.append("    main()")
        
        code = "\n".join(code_parts)
        
        # Write to file
        with open(output_file, "w") as f:
            f.write(code)
        
        os.chmod(output_file, 0o755)
        
        return {
            "success": True,
            "script_name": script_name,
            "file_path": output_file,
            "analysis_type": analysis_type,
            "message": f"Generated analysis script: {script_name}"
        }
        
    except Exception as e:
        logger.error(f"Failed to generate analysis script {script_name}: {e}")
        return {
            "success": False,
            "script_name": script_name,
            "error": str(e)
        }


@tool
def validate_python_code(
    code: str,
    check_imports: bool = True
) -> Dict[str, Any]:
    """
    Validate Python code syntax and imports.
    
    Args:
        code: Python code to validate
        check_imports: Whether to check if imports are available
        
    Returns:
        Dict with validation results
    """
    try:
        # Check syntax
        try:
            ast.parse(code)
            syntax_valid = True
            syntax_errors = []
        except SyntaxError as e:
            syntax_valid = False
            syntax_errors = [f"Line {e.lineno}: {e.msg}"]
        
        # Extract and check imports
        import_issues = []
        if check_imports and syntax_valid:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        try:
                            __import__(alias.name)
                        except ImportError:
                            import_issues.append(f"Module not available: {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    try:
                        __import__(node.module)
                    except (ImportError, TypeError):
                        import_issues.append(f"Module not available: {node.module}")
        
        return {
            "success": syntax_valid and len(import_issues) == 0,
            "syntax_valid": syntax_valid,
            "syntax_errors": syntax_errors,
            "import_issues": import_issues,
            "message": "Validation complete"
        }
        
    except Exception as e:
        logger.error(f"Code validation failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@tool
def validate_tcl_code(
    code: str,
    target_program: str = "vmd"
) -> Dict[str, Any]:
    """
    Basic validation of TCL code structure.
    
    Args:
        code: TCL code to validate
        target_program: Target program (vmd, namd, etc.)
        
    Returns:
        Dict with validation results
    """
    try:
        # Basic checks
        issues = []
        
        # Check for balanced braces
        open_braces = code.count("{")
        close_braces = code.count("}")
        if open_braces != close_braces:
            issues.append(f"Unbalanced braces: {open_braces} open, {close_braces} close")
        
        # Check for shebang if standalone
        if not code.startswith("#!") and not code.startswith("#!/"):
            issues.append("Missing shebang line (#!/usr/bin/env tclsh)")
        
        # Program-specific checks
        if target_program == "vmd":
            if "mol load" not in code and "mol new" not in code:
                issues.append("VMD script should load a molecule")
        
        return {
            "success": len(issues) == 0,
            "issues": issues,
            "target_program": target_program,
            "message": "TCL validation complete"
        }
        
    except Exception as e:
        logger.error(f"TCL validation failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }


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
        generate_analysis_script,
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
        self.working_directory = self.config.get("working_directory", "working_dir/programmer")
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
            # Add working directory if not specified
            if "working_dir" not in tool_params:
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
