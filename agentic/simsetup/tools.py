"""  
Simulation Setup Tools for GROMACS MD System Preparation
Thin wrapper that exposes modular @tool functions from src/simsetup/
"""
import logging
import os
from typing import Dict, Any, Optional
from pathlib import Path
from functools import wraps

# Import modular @tool functions from src/simsetup/
from src.simsetup.topology_builder import build_topology
from src.simsetup.ligand_topology import generate_ligand_parameters
from src.simsetup.amber_to_gromacs_converter import convert_amber_to_gromacs
from src.simsetup.box_builder import build_simulation_box
from src.simsetup.solvator import solvate_system
from src.simsetup.ion_adder import add_ions
from src.simsetup.mdp_generator import generate_mdp_files
from src.simsetup.tpr_generator import generate_tpr_file

# New modular tools for component-based workflow
from src.simsetup.pdb_to_gro_converter import convert_pdb_to_gro, split_complex_pdb_to_gro
from src.simsetup.gro_merger import merge_gro_files
from src.simsetup.topology_editor import edit_topology_file
from src.simsetup.atom_name_mapper import map_ligand_atom_names
from src.simsetup.system_builder import build_simulation_system

# Export tool functions for direct access
__all__ = [
    "SimulationSetupToolExecutor",
    "build_topology",
    "generate_ligand_parameters",
    "convert_amber_to_gromacs",
    "build_simulation_box",
    "solvate_system",
    "add_ions",
    "generate_mdp_files",
    "generate_tpr_file",
    # New component-based tools
    "convert_pdb_to_gro",
    "split_complex_pdb_to_gro",
    "merge_gro_files",
    "edit_topology_file",
    "map_ligand_atom_names",
    "build_simulation_system",
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
        # Core topology and parameter generation
        build_topology,
        generate_ligand_parameters,
        convert_amber_to_gromacs,
        # System building and solvation
        build_simulation_box,
        solvate_system,
        add_ions,
        generate_tpr_file,
        generate_mdp_files,
        # Component-based workflow tools
        convert_pdb_to_gro,
        split_complex_pdb_to_gro,
        merge_gro_files,
        edit_topology_file,
        map_ligand_atom_names,
        # High-level orchestrator
        build_simulation_system,
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
        
        # Tool map for built-in tools
        self.tool_map = {
            # Core tools
            "build_topology": build_topology,
            "generate_ligand_parameters": generate_ligand_parameters,
            "convert_amber_to_gromacs": convert_amber_to_gromacs,
            "build_simulation_box": build_simulation_box,
            "solvate_system": solvate_system,
            "add_ions": add_ions,
            "generate_mdp_files": generate_mdp_files,
            "generate_tpr_file": generate_tpr_file,
            # Component-based workflow tools
            "convert_pdb_to_gro": convert_pdb_to_gro,
            "split_complex_pdb_to_gro": split_complex_pdb_to_gro,
            "merge_gro_files": merge_gro_files,
            "edit_topology_file": edit_topology_file,
            "map_ligand_atom_names": map_ligand_atom_names,
            "build_simulation_system": build_simulation_system,
        }
        
        # Load programmer-generated tools
        self._load_programmer_tools()
        
        self.logger.info(f"SimulationSetupToolExecutor initialized with {len(self.tool_map)} tools (working_dir: {self.working_dir})")
    
    def _wrap_tool_for_working_dir(self, tool_func, tool_name: str):
        """
        Wrap a programmer-generated tool to execute in the agent's working directory.
        This ensures all file outputs go to working_dir/simsetup.
        
        Args:
            tool_func: The tool function to wrap
            tool_name: Name of the tool (for logging)
            
        Returns:
            Wrapped function that executes in the agent's working directory
        """
        # Get the actual function if it's a StructuredTool
        actual_func = tool_func.func if hasattr(tool_func, 'func') else tool_func
        
        @wraps(actual_func)
        def wrapped_tool(**kwargs):
            """
            Execute tool in the agent's working directory context.
            Changes to working_dir before execution and restores original directory after.
            """
            original_dir = os.getcwd()
            try:
                # Change to agent's working directory  
                os.chdir(self.working_dir)
                self.logger.debug(f"Executing {tool_name} in directory: {self.working_dir}")
                
                # Execute the tool
                if hasattr(tool_func, 'func'):
                    result = tool_func.func(**kwargs)
                elif hasattr(tool_func, 'invoke'):
                    result = tool_func.invoke(kwargs)
                else:
                    result = tool_func(**kwargs)
                
                return result
            finally:
                # Always restore original directory
                os.chdir(original_dir)
        
        # Preserve StructuredTool attributes if needed
        if hasattr(tool_func, 'name'):
            wrapped_tool.name = tool_func.name
        if hasattr(tool_func, 'description'):
            wrapped_tool.description = tool_func.description
        if hasattr(tool_func, 'args_schema'):
            wrapped_tool.args_schema = tool_func.args_schema
            
        return wrapped_tool
    
    def _load_programmer_tools(self):
        """Load dynamically generated tools from programmer agent."""
        try:
            from agentic.utils import get_dynamic_tool_loader
            
            tool_loader = get_dynamic_tool_loader(refresh=True)
            programmer_tools = tool_loader.get_tools_for_agent("simsetup")
            
            if programmer_tools:
                self.logger.info(f"Loading {len(programmer_tools)} programmer-generated tools for simsetup agent")
                for tool_name, tool_func in programmer_tools.items():
                    # Wrap the tool to execute in the agent's working directory
                    wrapped_tool = self._wrap_tool_for_working_dir(tool_func, tool_name)
                    self.tool_map[tool_name] = wrapped_tool
                    self.logger.info(f"  Registered programmer tool: {tool_name} (wrapped for {self.working_dir})")
            else:
                self.logger.debug("No programmer-generated tools found")
                
        except Exception as e:
            self.logger.warning(f"Failed to load programmer tools: {e}")
        
    def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a simulation setup tool by name.
        
        Args:
            tool_name: Name of tool to execute
            params: Tool parameters
            
        Returns:
            Dict with 'success', 'error', and tool-specific results
        """
        tool_func = self.tool_map.get(tool_name)
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
    
    def generate_ligand_parameters(self, ligand_pdb: str, output_dir: str,
                                   charge_method: str = "bcc", net_charge: Optional[int] = None,
                                   atom_type: str = "gaff2", preferred_tool: str = "acpype",
                                   **kwargs) -> Dict[str, Any]:
        """Generate ligand topology using ACPYPE/Antechamber - delegates to @tool function"""
        return generate_ligand_parameters.func(ligand_pdb=ligand_pdb, output_dir=output_dir,
                                              charge_method=charge_method, net_charge=net_charge,
                                              atom_type=atom_type, preferred_tool=preferred_tool, 
                                              **kwargs)
    
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
    
    def generate_mdp_files(self, output_dir: str, force_field: str = "amber99sb-ildn",
                          temperature: float = 310.0, pressure: float = 1.0,
                          has_ligand: bool = False, has_ions: bool = False,
                          production_ns: float = 200.0, **kwargs) -> Dict[str, Any]:
        """Generate all MDP parameter files for simulation workflow - delegates to @tool function"""
        return generate_mdp_files.func(output_dir=output_dir, force_field=force_field,
                                      temperature=temperature, pressure=pressure,
                                      has_ligand=has_ligand, has_ions=has_ions,
                                      production_ns=production_ns, **kwargs)
