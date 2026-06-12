"""
Pydantic schemas for simulation setup validation and workflow orchestration.

Note: Tool-level input validation is handled automatically by LangChain's @tool decorator.
This file only contains workflow orchestration schemas for agent-level coordination.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


# ========== Workflow Orchestration Schemas ==========

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
    production_ns: Optional[float] = Field(default=None, description="Production simulation length (ns)")
    extended_minimization: bool = Field(
        default=False,
        description="Two-stage minim (minim + minim2) for remodelled/strained structures",
    )
    user_goal: str = Field(default="", description="User's simulation goals")
    additional_instructions: Optional[str] = Field(None, description="Planner's detailed instructions for this agent")
    component_selection: Optional[Dict[str, Any]] = Field(
        default=None,
        description="User-specified component selection: {protein: bool, ligand: bool, ions: bool, water: bool}"
    )


class SimSetupAgentOutput(BaseModel):
    """Output from simulation setup agent - mirrors PreprocessingAgentOutput"""
    success: bool = Field(..., description="Overall success status")
    plan: SimSetupPlan = Field(..., description="LLM-generated setup plan")
    result: SimSetupResult = Field(..., description="Execution results")
    supervisor_update: Dict[str, Any] = Field(default_factory=dict, description="Updates for workflow state")
