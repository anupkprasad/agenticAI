"""GROMACS MDP file generation"""
import os
import logging
from typing import Dict, Any, Optional
from langchain.tools import tool

logger = logging.getLogger(__name__)


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
    - nvt: NVT equilibration
    - npt: NPT equilibration
    - md: Production MD run
    
    Args:
        mdp_type: Type of MDP file (minimization, nvt, npt, md)
        parameters: MDP parameters {param_name: value}
        force_field: Force field being used
        output_file: Output file path
        working_dir: Working directory
        
    Returns:
        Dict with generation results
    """
    try:
        if not working_dir:
            working_dir = "working_dir/programmer"
        
        mdp_dir = os.path.join(working_dir, "mdp")
        os.makedirs(mdp_dir, exist_ok=True)
        
        if not output_file:
            output_file = os.path.join(mdp_dir, f"{mdp_type}.mdp")
        
        lines = []
        lines.append(f"; MDP file for {mdp_type}")
        lines.append(f"; Force field: {force_field}")
        lines.append("")
        
        for key, value in parameters.items():
            if isinstance(value, dict) and "comment" in value:
                lines.append(f"; {value['comment']}")
                lines.append(f"{key} = {value['value']}")
            else:
                lines.append(f"{key} = {value}")
            lines.append("")
        
        content = "\n".join(lines)
        
        with open(output_file, "w") as f:
            f.write(content)
        
        return {
            "success": True,
            "mdp_type": mdp_type,
            "file_path": output_file,
            "force_field": force_field
        }
        
    except Exception as e:
        logger.error(f"Failed to generate MDP file: {e}")
        return {
            "success": False,
            "error": str(e)
        }
