"""
Preprocessing Tools for PDB Structure Preparation
Thin wrapper that exposes modular @tool functions from src/preprocess/ and src/utils/
"""
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# Import modular @tool functions from src/utils/ and src/preprocess/
from src.utils.pdb_analyzer import analyze_pdb
from src.preprocess.hydrogen_adder import add_hydrogens
from src.preprocess.structure_validator import validate_structure
from src.preprocess.complex_separator import separate_protein_ligand, separate_complex_components

# Export tool functions for direct access
__all__ = [
    "PreprocessingToolExecutor",
    "analyze_pdb",
    "add_hydrogens",
    "validate_structure",
    "separate_protein_ligand",
    "separate_complex_components",
    "get_preprocessing_tools",
    "get_tool_metadata",
]

logger = logging.getLogger(__name__)


def get_preprocessing_tools() -> list:
    """
    Get all preprocessing @tool functions for LLM binding.
    These StructuredTool objects can be passed directly to LLM.bind_tools()
    
    Returns:
        List of StructuredTool objects ready for LLM use
    """
    return [
        analyze_pdb,
        separate_complex_components,
        separate_protein_ligand,
        add_hydrogens,
        validate_structure,
    ]


def get_tool_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Dynamically extract metadata from all @tool functions.
    This replaces manual tool definitions in config.yaml
    
    Returns:
        Dict mapping tool names to their metadata (description, args, etc.)
    """
    tools = get_preprocessing_tools()
    metadata = {}
    
    for tool in tools:
        # StructuredTool has .name, .description, .args_schema attributes
        tool_info = {
            "name": tool.name,
            "description": tool.description,
            "args": {},
        }
        
        # Extract argument schema if available
        if hasattr(tool, 'args_schema') and tool.args_schema:
            schema = tool.args_schema.schema()
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


class PreprocessingToolExecutor:
    """
    Thin wrapper that delegates to modular @tool functions in src/preprocess/.
    All heavy logic has been moved to individual tool modules.
    """
    
    def __init__(self, working_dir: str = "working_dir", config: Optional[Dict[str, Any]] = None):
        """
        Initialize tool executor
        
        Args:
            working_dir: Directory for intermediate files
            config: Configuration dictionary from config.yaml
        """
        self.working_dir = Path(working_dir)
        self.working_dir.mkdir(parents=True, exist_ok=True)
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        
    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a preprocessing tool by name.
        
        Args:
            tool_name: Name of tool to execute
            params: Tool parameters
            
        Returns:
            Dict with 'success', 'error', and tool-specific results
        """
        tool_map = {
            "analyze_pdb": analyze_pdb,
            "separate_complex_components": separate_complex_components,
            "separate_protein_ligand": separate_protein_ligand,
            "add_hydrogens": add_hydrogens,
            "validate_structure": validate_structure,
        }
        
        tool_func = tool_map.get(tool_name)
        if not tool_func:
            return {
                "success": False,
                "error": f"Unknown tool: {tool_name}"
            }
        
        try:
            # StructuredTool objects need .func or .invoke() to execute
            if hasattr(tool_func, 'func'):
                # @tool decorator wraps function in StructuredTool - call .func directly
                result = tool_func.func(**params)
            elif hasattr(tool_func, 'invoke'):
                # Alternative: use LangChain's invoke method (passes dict)
                result = tool_func.invoke(params)
            else:
                # Direct function call (backward compatibility)
                result = tool_func(**params)
            
            # Ensure result is a dict with at least 'success' key
            if not isinstance(result, dict):
                return {
                    "success": False,
                    "error": f"Tool {tool_name} returned non-dict result: {type(result)}"
                }
            
            return result
            
        except Exception as e:
            self.logger.error(f"Tool execution failed: {tool_name}: {e}")
            import traceback
            traceback.print_exc()
            return {
                "success": False,
                "error": str(e)
            }
    
    # Convenience methods that delegate to @tool functions
    # Note: @tool decorators wrap functions in StructuredTool, access via .func
    def analyze_pdb(self, pdb_file: str, **kwargs) -> Dict[str, Any]:
        """Analyze PDB file structure - delegates to @tool function"""
        return analyze_pdb.func(pdb_file=pdb_file, **kwargs)
    
    def separate_complex_components(self, pdb_file: str, output_dir: Optional[str] = None,
                                   protein_output: Optional[str] = None,
                                   ligand_output: Optional[str] = None,
                                   ion_output: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Separate protein, ligand, and ion components - delegates to @tool function"""
        return separate_complex_components.func(pdb_file=pdb_file, output_dir=output_dir,
                                               protein_output=protein_output,
                                               ligand_output=ligand_output,
                                               ion_output=ion_output, **kwargs)
    
    def separate_protein_ligand(self, pdb_file: str, protein_output: Optional[str] = None,
                               ligand_output: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Separate protein and ligand components - delegates to @tool function"""
        return separate_protein_ligand.func(pdb_file=pdb_file, protein_output=protein_output,
                                          ligand_output=ligand_output, **kwargs)
    
    def add_hydrogens(self, pdb_file: str, output_file: Optional[str] = None, 
                     method: str = "auto", ph: float = 7.4, molecule_type: str = "auto", **kwargs) -> Dict[str, Any]:
        """Add missing hydrogens - delegates to @tool function"""
        return add_hydrogens.func(pdb_file=pdb_file, output_file=output_file, method=method, 
                                ph=ph, molecule_type=molecule_type, **kwargs)
    
    def validate_structure(self, pdb_file: str, **kwargs) -> Dict[str, Any]:
        """Validate PDB structure - delegates to @tool function"""
        return validate_structure.func(pdb_file=pdb_file, **kwargs)
