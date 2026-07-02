"""
Pydantic schemas for MD trajectory analysis validation.

Note: Tool-level input validation is handled automatically by LangChain's @tool decorator.
This file contains workflow orchestration schemas and result models for agent-level coordination.
"""
from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field


# ========== Result Schemas (used for structured outputs) ==========

class AnalysisResult(BaseModel):
    """Output schema for analysis results"""
    success: bool = Field(..., description="Whether analysis succeeded")
    message: str = Field(..., description="Summary message")
    data: Optional[Dict[str, Any]] = Field(None, description="Analysis data")
    output_files: Optional[List[str]] = Field(None, description="Generated output files")
    errors: Optional[List[str]] = Field(None, description="Error messages if failed")


class RMSDResult(BaseModel):
    """Output schema for RMSD analysis results"""
    success: bool
    mean_rmsd: Optional[float] = Field(None, description="Mean RMSD in Angstroms")
    std_rmsd: Optional[float] = Field(None, description="Standard deviation of RMSD")
    min_rmsd: Optional[float] = Field(None, description="Minimum RMSD")
    max_rmsd: Optional[float] = Field(None, description="Maximum RMSD")
    n_frames: Optional[int] = Field(None, description="Number of frames analyzed")
    selection: Optional[str] = Field(None, description="Atom selection used")
    output_file: Optional[str] = Field(None, description="Output file path")
    message: str = Field(..., description="Result message")
    error: Optional[str] = Field(None, description="Error message if failed")


class RMSFResult(BaseModel):
    """Output schema for RMSF analysis results"""
    success: bool
    mean_rmsf: Optional[float] = Field(None, description="Mean RMSF in Angstroms")
    std_rmsf: Optional[float] = Field(None, description="Standard deviation of RMSF")
    min_rmsf: Optional[float] = Field(None, description="Minimum RMSF")
    max_rmsf: Optional[float] = Field(None, description="Maximum RMSF")
    n_residues: Optional[int] = Field(None, description="Number of residues analyzed")
    most_flexible: Optional[List[Dict[str, Any]]] = Field(
        None, description="Most flexible residues"
    )
    least_flexible: Optional[List[Dict[str, Any]]] = Field(
        None, description="Least flexible residues"
    )
    selection: Optional[str] = Field(None, description="Atom selection used")
    output_file: Optional[str] = Field(None, description="Output file path")
    message: str = Field(..., description="Result message")
    error: Optional[str] = Field(None, description="Error message if failed")


class GyrationResult(BaseModel):
    """Output schema for radius of gyration results"""
    success: bool
    mean_rg: Optional[float] = Field(None, description="Mean Rg in Angstroms")
    std_rg: Optional[float] = Field(None, description="Standard deviation of Rg")
    min_rg: Optional[float] = Field(None, description="Minimum Rg")
    max_rg: Optional[float] = Field(None, description="Maximum Rg")
    n_frames: Optional[int] = Field(None, description="Number of frames analyzed")
    selection: Optional[str] = Field(None, description="Atom selection used")
    output_file: Optional[str] = Field(None, description="Output file path")
    message: str = Field(..., description="Result message")
    error: Optional[str] = Field(None, description="Error message if failed")


class EnergyResult(BaseModel):
    """Output schema for energy analysis results"""
    success: bool
    n_frames: Optional[int] = Field(None, description="Number of frames analyzed")
    terms: Optional[Dict[str, Dict[str, float]]] = Field(
        None, description="Energy term statistics"
    )
    output_file: Optional[str] = Field(None, description="Output file path")
    message: str = Field(..., description="Result message")
    error: Optional[str] = Field(None, description="Error message if failed")


class AnalysisWorkflowInput(BaseModel):
    """Input schema for complete analysis workflow"""
    topology_file: str = Field(..., description="Topology file")
    trajectory_file: str = Field(..., description="Trajectory file")
    energy_file: Optional[str] = Field(None, description="Energy file (.edr)")
    analyses: List[Literal["rmsd", "rmsf", "gyration", "energy"]] = Field(
        default=["rmsd", "rmsf"],
        description="List of analyses to perform"
    )
    selection: str = Field(
        default="protein and name CA",
        description="Default atom selection"
    )
    working_dir: str = Field(
        default="./working_dir/analysis",
        description="Working directory for analysis outputs"
    )
    generate_plots: bool = Field(
        default=True,
        description="Whether to generate visualization plots"
    )


class AnalysisWorkflowOutput(BaseModel):
    """Output schema for complete analysis workflow"""
    success: bool
    analyses_completed: List[str] = Field(..., description="List of completed analyses")
    results: Dict[str, Any] = Field(..., description="Results for each analysis")
    output_directory: str = Field(..., description="Directory with output files")
    summary: str = Field(..., description="Overall analysis summary")
    errors: Optional[List[str]] = Field(None, description="Any errors encountered")


# ========== Workflow Orchestration Schemas (matching simsetup agent) ==========

class AnalysisStep(BaseModel):
    """Single step in analysis plan - mirrors SimSetupStep"""
    name: str = Field(..., description="Human-readable step name")
    description: str = Field(..., description="What this step does")
    tool_name: str = Field(..., description="Tool function to call")
    tool_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for tool")
    reason: str = Field(..., description="Why this step is needed")


class AnalysisPlan(BaseModel):
    """LLM-generated analysis plan - mirrors SimSetupPlan"""
    reasoning: str = Field(..., description="LLM's reasoning for this plan")
    overview: str = Field(..., description="High-level summary of analysis approach")
    steps: List[AnalysisStep] = Field(..., description="Ordered list of analysis steps")
    potential_issues: List[str] = Field(default_factory=list, description="Issues to watch for")
    recommendations: List[str] = Field(default_factory=list, description="Best practice recommendations")


class AnalysisResult(BaseModel):
    """Execution result of analysis plan - mirrors SimSetupResult"""
    success: bool = Field(..., description="Overall success status")
    analyses_completed: List[str] = Field(default_factory=list, description="Successfully completed analyses")
    results: Dict[str, Any] = Field(default_factory=dict, description="Results for each analysis")
    output_directory: str = Field(..., description="Directory with all outputs")
    report: str = Field(..., description="Execution summary report")
    issues: List[str] = Field(default_factory=list, description="Issues encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings during execution")
    generated_files: Dict[str, str] = Field(default_factory=dict, description="Map of file paths to descriptions")
    execution_log: str = Field(default="", description="Detailed execution log")


class AnalysisAgentInput(BaseModel):
    """Input to analysis agent - mirrors SimSetupAgentInput"""
    working_directory: str = Field(..., description="Base working directory")
    hpc_output_dir: str = Field(..., description="HPC results directory (trajectory/topology)")
    topology_file: Optional[str] = Field(None, description="Explicit topology file path")
    trajectory_file: Optional[str] = Field(None, description="Explicit trajectory file path")
    energy_file: Optional[str] = Field(None, description="Energy file path (.edr)")
    analyses: List[str] = Field(
        default=["rmsd", "rmsf", "gyration"],
        description="List of analyses to perform"
    )
    user_goal: str = Field(default="", description="User's analysis goals")
    enriched_goal: Optional[str] = Field(
        None,
        description="Per-simulation enriched goal from input validation (primary analysis scope)",
    )
    additional_instructions: Optional[str] = Field(None, description="Planner's detailed instructions for this agent")


class AnalysisAgentOutput(BaseModel):
    """Output from analysis agent - mirrors SimSetupAgentOutput"""
    success: bool = Field(..., description="Overall success status")
    plan: AnalysisPlan = Field(..., description="LLM-generated analysis plan")
    result: AnalysisResult = Field(..., description="Execution results")
    supervisor_update: Dict[str, Any] = Field(default_factory=dict, description="Updates for workflow state")
