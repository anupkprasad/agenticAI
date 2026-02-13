"""
Pydantic schemas for simulation setup validation and workflow orchestration
"""
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field, validator


class TopologyBuildInput(BaseModel):
    """Input schema for topology generation"""
    pdb_file: str = Field(..., description="Path to cleaned PDB file")
    force_field: str = Field(default="amber99sb-ildn", description="GROMACS force field")
    water_model: str = Field(default="tip3p", description="Water model (tip3p, spce, tip4p)")
    output_file: Optional[str] = Field(None, description="Output coordinate file path")
    topology_file: Optional[str] = Field(None, description="Output topology file path")


class BoxBuildInput(BaseModel):
    """Input schema for simulation box creation"""
    coordinate_file: str = Field(..., description="Input coordinate file (.gro)")
    box_type: Literal["cubic", "dodecahedron", "octahedron"] = Field(
        default="cubic", 
        description="Box shape"
    )
    box_distance: float = Field(default=1.0, description="Distance from solute to box edge (nm)")
    output_file: Optional[str] = Field(None, description="Output coordinate file")


class SolvateInput(BaseModel):
    """Input schema for system solvation"""
    coordinate_file: str = Field(..., description="Input coordinate file (.gro)")
    topology_file: str = Field(..., description="Topology file (.top)")
    water_model: str = Field(default="spc216", description="Water configuration")
    output_file: Optional[str] = Field(None, description="Output coordinate file")


class IonAdditionInput(BaseModel):
    """Input schema for ion addition"""
    coordinate_file: str = Field(..., description="Input coordinate file (.gro)")
    topology_file: str = Field(..., description="Topology file (.top)")
    mdp_file: str = Field(..., description="MDP parameter file for grompp")
    neutral: bool = Field(default=True, description="Neutralize system charge")
    concentration: float = Field(default=0.15, description="Salt concentration (M)")
    output_file: Optional[str] = Field(None, description="Output coordinate file")
    
    @validator("concentration")
    def validate_concentration(cls, v):
        if v < 0 or v > 2.0:
            raise ValueError("Concentration must be between 0 and 2.0 M")
        return v


class MDPGenerationInput(BaseModel):
    """Input schema for MDP file generation"""
    mdp_type: Literal["minim", "nvt", "npt", "md", "ions"] = Field(
        default="minim",
        description="Type of simulation"
    )
    temperature: float = Field(default=300.0, description="Temperature (K)")
    pressure: float = Field(default=1.0, description="Pressure (bar)")
    nsteps: int = Field(default=50000, description="Number of simulation steps")
    output_file: Optional[str] = Field(None, description="Output MDP file path")
    
    @validator("temperature")
    def validate_temperature(cls, v):
        if v < 0 or v > 1000:
            raise ValueError("Temperature must be between 0 and 1000 K")
        return v
    
    @validator("nsteps")
    def validate_nsteps(cls, v):
        if v < 0:
            raise ValueError("nsteps must be positive")
        return v


class AmberConversionInput(BaseModel):
    """Input schema for AMBER to GROMACS conversion"""
    prmtop_file: str = Field(..., description="AMBER parameter/topology file (.prmtop)")
    inpcrd_file: str = Field(..., description="AMBER coordinate file (.inpcrd/.rst7)")
    output_prefix: Optional[str] = Field(None, description="Output file prefix")


class SetupOutput(BaseModel):
    """Output schema for setup operations"""
    success: bool = Field(..., description="Operation success status")
    output_file: Optional[str] = Field(None, description="Primary output file")
    topology_file: Optional[str] = Field(None, description="Topology file if generated")
    message: str = Field(..., description="Status message")
    warnings: Optional[list] = Field(default_factory=list, description="Warning messages")
    error: Optional[str] = Field(None, description="Error message if failed")


# ========== Workflow Orchestration Schemas (matching preprocessing agent) ==========

class SimSetupStep(BaseModel):
    """Single step in simulation setup plan - mirrors PreprocessingStep"""
    name: str = Field(..., description="Human-readable step name")
    description: str = Field(..., description="What this step does")
    tool_name: str = Field(..., description="Tool function to call")
    tool_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for tool")
    reason: str = Field(..., description="Why this step is needed")


class SimSetupPlan(BaseModel):
    """LLM-generated simulation setup plan - mirrors PreprocessingPlan"""
    reasoning: str = Field(..., description="LLM's reasoning for this plan")
    overview: str = Field(..., description="High-level summary of setup approach")
    steps: List[SimSetupStep] = Field(..., description="Ordered list of setup steps")
    potential_issues: List[str] = Field(default_factory=list, description="Issues to watch for")
    recommendations: List[str] = Field(default_factory=list, description="Best practice recommendations")


class SimSetupResult(BaseModel):
    """Execution result of simulation setup plan - mirrors PreprocessingResult"""
    success: bool = Field(..., description="Overall success status")
    coordinates: Optional[str] = Field(None, description="Final coordinate file (e.g., system.gro)")
    topology: Optional[str] = Field(None, description="Final topology file (e.g., topol.top)")
    mdp_files: Dict[str, str] = Field(default_factory=dict, description="Generated MDP files by phase")
    box_dimensions: Optional[str] = Field(None, description="Simulation box dimensions")
    water_molecules: Optional[int] = Field(None, description="Number of water molecules added")
    ion_count: Optional[Dict[str, int]] = Field(None, description="Ions added (e.g., {'NA': 10, 'CL': 12})")
    report: str = Field(..., description="Execution summary report")
    issues: List[str] = Field(default_factory=list, description="Issues encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings during execution")
    generated_files: Dict[str, str] = Field(default_factory=dict, description="Map of file paths to descriptions")
    execution_log: str = Field(default="", description="Detailed execution log")


class SimSetupAgentInput(BaseModel):
    """Input to simulation setup agent - mirrors PreprocessingAgentInput"""
    cleaned_pdb: str = Field(..., description="Path to preprocessed PDB file")
    working_directory: str = Field(..., description="Base working directory")
    force_field: str = Field(default="amber99sb-ildn", description="GROMACS force field")
    water_model: str = Field(default="tip3p", description="Water model for simulation")
    temperature: float = Field(default=300.0, description="Simulation temperature (K)")
    pressure: float = Field(default=1.0, description="Simulation pressure (bar)")
    user_goal: str = Field(default="", description="User's simulation goals")
    additional_instructions: Optional[str] = Field(None, description="Planner's detailed instructions for this agent")


class SimSetupAgentOutput(BaseModel):
    """Output from simulation setup agent - mirrors PreprocessingAgentOutput"""
    success: bool = Field(..., description="Overall success status")
    plan: SimSetupPlan = Field(..., description="LLM-generated setup plan")
    result: SimSetupResult = Field(..., description="Execution results")
    supervisor_update: Dict[str, Any] = Field(default_factory=dict, description="Updates for workflow state")
