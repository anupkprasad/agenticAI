"""
Pydantic schemas for supervisor validation and orchestration.
Enables structured data handling for input validation and workflow coordination.
"""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ComponentSelection(BaseModel):
    """User's component selection for simulation"""
    protein: bool = Field(description="Include protein in simulation")
    ligand: bool = Field(description="Include ligand in simulation")
    water: bool = Field(description="Include water molecules")
    ions: bool = Field(description="Include ions")
    specific_chains: Optional[List[str]] = Field(default=None, description="Specific protein chains to include")


class FeasibilityValidation(BaseModel):
    """Result of feasibility validation"""
    is_feasible: bool = Field(description="Whether the requested workflow is feasible")
    errors: List[str] = Field(default_factory=list, description="Blocking errors that prevent execution")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking warnings")


class FileInfo(BaseModel):
    """File information for analysis tasks"""
    hpc_output_dir: str = Field(description="HPC output directory path")
    analysis_output_dir: str = Field(description="Analysis output directory path")
    topology_file: Optional[str] = Field(default=None, description="Path to topology file (.gro, .pdb, .tpr)")
    trajectory_file: Optional[str] = Field(default=None, description="Path to trajectory file (.xtc, .trr)")
    energy_file: Optional[str] = Field(default=None, description="Path to energy file (.edr)")


class TaskRequirements(BaseModel):
    """Required inputs for different task types"""
    pdb_required: bool = Field(description="Whether PDB file is required")
    pdb_analysis_required: bool = Field(description="Whether PDB analysis is required")
    trajectory_path_required: bool = Field(description="Whether trajectory path is required")
    topology_required: bool = Field(description="Whether topology file is required")


class SupervisorInput(BaseModel):
    """Input to supervisor node"""
    user_goal: str = Field(description="User's natural language goal")
    working_directory: str = Field(description="Working directory for files")
    subtask_type: Optional[str] = Field(default="full_task", description="Type of subtask: full_task, preprocess_only, setup_only, analysis_only")
    force_field: Optional[str] = Field(default="amber99sb-ildn", description="Force field for simulations")
    water_model: Optional[str] = Field(default="tip3p", description="Water model")


class SupervisorOutput(BaseModel):
    """Output from supervisor validation/routing"""
    next_node: str = Field(description="Next workflow node to execute")
    structured_prompt: Optional[str] = Field(default=None, description="Enriched prompt with context")
    pdb_analysis: Optional[Dict[str, Any]] = Field(default=None, description="PDB structure analysis")
    component_selection: Optional[ComponentSelection] = Field(default=None, description="Parsed component selection")
    file_info: Optional[FileInfo] = Field(default=None, description="File information for analysis tasks")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings generated")
