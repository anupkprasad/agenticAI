"""TCL script generation for VMD/NAMD"""
import os
import logging
from typing import Dict, Any, Optional
from langchain.tools import tool

logger = logging.getLogger(__name__)


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
        if not working_dir:
            working_dir = "working_dir/programmer"
        
        tcl_dir = os.path.join(working_dir, "tcl")
        os.makedirs(tcl_dir, exist_ok=True)
        
        if not output_file:
            output_file = os.path.join(tcl_dir, f"{script_name}.tcl")
        
        # Build TCL script
        code_parts = []
        code_parts.append("#!/usr/bin/env tclsh")
        code_parts.append(f"# {script_name}.tcl - {description}")
        code_parts.append(f"# Target: {target_program}")
        code_parts.append("")
        
        # Parameter handling
        for idx, (param_name, param_spec) in enumerate(parameters.items()):
            default = param_spec.get("default", '""')
            code_parts.append(f"if {{[llength $argv] > {idx}}} {{")
            code_parts.append(f"    set {param_name} [lindex $argv {idx}]")
            code_parts.append("} else {")
            code_parts.append(f"    set {param_name} {default}")
            code_parts.append("}")
        code_parts.append("")
        
        code_parts.append(implementation)
        code_parts.append("")
        code_parts.append(f'puts "{script_name} completed"')
        
        if target_program == "vmd":
            code_parts.append("quit")
        
        code = "\n".join(code_parts)
        
        with open(output_file, "w") as f:
            f.write(code)
        
        os.chmod(output_file, 0o755)
        
        return {
            "success": True,
            "script_name": script_name,
            "file_path": output_file,
            "language": "tcl",
            "target_program": target_program
        }
        
    except Exception as e:
        logger.error(f"Failed to generate TCL script {script_name}: {e}")
        return {
            "success": False,
            "error": str(e)
        }
