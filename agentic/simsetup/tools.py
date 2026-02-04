"""
Simulation Setup Tools for GROMACS MD System Preparation
Thin wrapper that exposes modular @tool functions from src/simsetup/
"""
import logging
from typing import Dict, Any, Optional
from pathlib import Path

# Import modular @tool functions from src/simsetup/
from src.simsetup.topology_builder import build_topology
from src.simsetup.ligand_topology_generator import generate_ligand_topology
from src.simsetup.amber_to_gromacs_converter import convert_amber_to_gromacs
from src.simsetup.box_builder import build_simulation_box
from src.simsetup.solvator import solvate_system
from src.simsetup.ion_adder import add_ions
from src.simsetup.mdp_generator import generate_mdp_file

# Export tool functions for direct access
__all__ = [
    "SimulationSetupToolExecutor",
    "build_topology",
    "generate_ligand_topology",
    "convert_amber_to_gromacs",
    "build_simulation_box",
    "solvate_system",
    "add_ions",
    "generate_mdp_file",
    "get_simulation_setup_tools",
    "get_tool_metadata",
]

logger = logging.getLogger(__name__)


def get_simulation_setup_tools() -> list:
    """
    Get all simulation setup @tool functions for LLM binding.
    These StructuredTool objects can be passed directly to LLM.bind_tools()
    
    Returns:
        List of StructuredTool objects ready for LLM use
    """
    return [
        build_topology,
        generate_ligand_topology,
        convert_amber_to_gromacs,
        build_simulation_box,
        solvate_system,
        add_ions,
        generate_mdp_file,
    ]


def get_tool_metadata() -> Dict[str, Dict[str, Any]]:
    """
    Dynamically extract metadata from all @tool functions.
    This replaces manual tool definitions in config.yaml
    
    Returns:
        Dict mapping tool names to their metadata (description, args, etc.)
    """
    tools = get_simulation_setup_tools()
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


class SimulationSetupToolExecutor:
    """
    Thin wrapper that delegates to modular @tool functions in src/simsetup/.
    Handles topology generation, system setup, solvation, and parameter file creation.
    """
    
    def __init__(self, working_dir: str = "working_dir", config: Optional[Dict[str, Any]] = None):
        """
        Initialize setup tool executor
        
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
        Execute a simulation setup tool by name.
        
        Args:
            tool_name: Name of tool to execute
            params: Tool parameters
            
        Returns:
            Dict with 'success', 'error', and tool-specific results
        """
        tool_map = {
            "build_topology": build_topology,
            "generate_ligand_topology": generate_ligand_topology,
            "convert_amber_to_gromacs": convert_amber_to_gromacs,
            "build_simulation_box": build_simulation_box,
            "solvate_system": solvate_system,
            "add_ions": add_ions,
            "generate_mdp_file": generate_mdp_file,
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
                # @tool decorator wraps function in StructuredTool
                return tool_func.func(**params)
            elif hasattr(tool_func, 'invoke'):
                # Alternative: use LangChain's invoke method
                return tool_func.invoke(params)
            else:
                # Direct function call (backward compatibility)
                return tool_func(**params)
        except Exception as e:
            self.logger.error(f"Tool execution failed: {tool_name}: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    # Convenience methods that delegate to @tool functions
    # Note: @tool decorators wrap functions in StructuredTool, access via .func
    def build_topology(self, pdb_file: str, force_field: str = "amber99sb-ildn",
                      water_model: str = "tip3p", output_file: Optional[str] = None, 
                      **kwargs) -> Dict[str, Any]:
        """Generate GROMACS topology using gmx pdb2gmx - delegates to @tool function"""
        return build_topology.func(pdb_file=pdb_file, force_field=force_field, 
                            water_model=water_model, output_file=output_file, **kwargs)
    
    def generate_ligand_topology(self, pdb_file: str, ligand_name: str, charge: int,
                                output_dir: Optional[str] = None, force_field: str = "gaff2",
                                preferred_method: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Generate ligand topology using ACPYPE/Antechamber - delegates to @tool function"""
        return generate_ligand_topology.func(pdb_file=pdb_file, ligand_name=ligand_name, 
                                       charge=charge, output_dir=output_dir,
                                       force_field=force_field, preferred_method=preferred_method, **kwargs)
    
    def convert_amber_to_gromacs(self, prmtop_file: str, inpcrd_file: str,
                                output_prefix: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Convert AMBER files to GROMACS format - delegates to @tool function"""
        return convert_amber_to_gromacs.func(prmtop_file=prmtop_file, inpcrd_file=inpcrd_file,
                                       output_prefix=output_prefix, **kwargs)
    
    def build_simulation_box(self, coordinate_file: str, box_type: str = "cubic",
                           box_distance: float = 1.0, output_file: Optional[str] = None,
                           **kwargs) -> Dict[str, Any]:
        """Create simulation box using gmx editconf - delegates to @tool function"""
        return build_simulation_box.func(coordinate_file=coordinate_file, box_type=box_type,
                                   box_distance=box_distance, output_file=output_file, **kwargs)
    
    def solvate_system(self, coordinate_file: str, topology_file: str,
                      water_model: str = "spc216", output_file: Optional[str] = None,
                      **kwargs) -> Dict[str, Any]:
        """Add water molecules using gmx solvate - delegates to @tool function"""
        return solvate_system.func(coordinate_file=coordinate_file, topology_file=topology_file,
                            water_model=water_model, output_file=output_file, **kwargs)
    
    def add_ions(self, coordinate_file: str, topology_file: str, mdp_file: str,
                neutral: bool = True, concentration: float = 0.15, 
                output_file: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Add ions for neutralization and salt concentration - delegates to @tool function"""
        return add_ions.func(coordinate_file=coordinate_file, topology_file=topology_file,
                       mdp_file=mdp_file, neutral=neutral, concentration=concentration,
                       output_file=output_file, **kwargs)
    
    def generate_mdp_file(self, mdp_type: str = "minim", temperature: float = 300.0,
                         pressure: float = 1.0, nsteps: int = 50000,
                         output_file: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Generate MDP parameter file - delegates to @tool function"""
        return generate_mdp_file.func(mdp_type=mdp_type, temperature=temperature,
                                pressure=pressure, nsteps=nsteps, output_file=output_file, **kwargs)
