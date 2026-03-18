"""Python tool generation functionality"""
import os
import ast
import logging
from pathlib import Path
from typing import Dict, Any, Optional
from langchain.tools import tool

logger = logging.getLogger(__name__)


def extract_imports_from_code(code: str) -> tuple[set[str], str]:
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
        impl_imports, cleaned_implementation = extract_imports_from_code(implementation)
        
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
        code_parts.append('"""')
        
        # Add all imports (sorted for consistency)
        for imp in sorted(all_imports):
            code_parts.append(imp)
        
        code_parts.append("")
        code_parts.append("logger = logging.getLogger(__name__)")
        code_parts.append("")
        
        # Add path resolution helper function
        code_parts.append('def _resolve_input_path(file_ref: str, param_name: str = "input") -> Path:')
        code_parts.append('    """Resolve file reference to absolute path with validation."""')
        code_parts.append('    file_path = Path(file_ref)')
        code_parts.append('    if file_path.is_absolute():')
        code_parts.append('        if file_path.exists():')
        code_parts.append('            return file_path')
        code_parts.append('        else:')
        code_parts.append('            raise FileNotFoundError(f"{param_name} file not found: {file_ref}")')
        code_parts.append('    if file_path.exists():')
        code_parts.append('        return file_path.resolve()')
        code_parts.append('    raise FileNotFoundError(f"{param_name} file not found: {file_ref}")')
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
        code_parts.append("        original_dir = None")
        code_parts.append("        if working_dir:")
        code_parts.append("            os.makedirs(working_dir, exist_ok=True)")
        code_parts.append("            originaldir = os.getcwd()")
        code_parts.append("            os.chdir(working_dir)")
        code_parts.append("        ")
        # Indent implementation
        for line in cleaned_implementation.split("\n"):
            if line.strip():
                code_parts.append("        " + line)
            elif code_parts[-1].strip():
                code_parts.append("        ")
        code_parts.append("")
        code_parts.append("        if original_dir:")
        code_parts.append("            os.chdir(original_dir)")
        code_parts.append("        return {")
        code_parts.append('            "success": True,')
        code_parts.append(f'            "tool": "{tool_name}"')
        code_parts.append("        }")
        code_parts.append("    except Exception as e:")
        code_parts.append("        if 'original_dir' in locals() and original_dir:")
        code_parts.append("            os.chdir(original_dir)")
        code_parts.append(f'        logger.error("Tool {tool_name} failed: " + str(e))')
        code_parts.append("        return {")
        code_parts.append('            "success": False,')
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
            "has_decorator": add_langchain_decorator
        }
        
    except Exception as e:
        logger.error(f"Failed to generate Python tool {tool_name}: {e}")
        return {
            "success": False,
            "tool_name": tool_name,
            "error": str(e)
        }
