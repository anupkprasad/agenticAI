"""Code validation tools"""
import ast
import logging
from typing import Dict, Any
from langchain.tools import tool

logger = logging.getLogger(__name__)


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
            "import_issues": import_issues
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
        issues = []
        
        # Check for balanced braces
        open_braces = code.count("{")
        close_braces = code.count("}")
        if open_braces != close_braces:
            issues.append(f"Unbalanced braces: {open_braces} open, {close_braces} close")
        
        # Program-specific checks
        if target_program == "vmd":
            if "mol load" not in code and "mol new" not in code:
                issues.append("VMD script should load a molecule")
        
        return {
            "success": len(issues) == 0,
            "issues": issues,
            "target_program": target_program
        }
        
    except Exception as e:
        logger.error(f"TCL validation failed: {e}")
        return {
            "success": False,
            "error": str(e)
        }
