"""
Pydantic schemas for programmer tools and LLM agent calls.
Enables structured tool calling with LLM agents for code generation.

This follows the same pattern as analysis, preprocess, simsetup, and hpc agents.
"""
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field


# ========== Tool Specification Schemas ==========

class ToolSpecification(BaseModel):
    """Specification for a tool to be created"""
    name: str = Field(description="Name of the tool/function")
    description: str = Field(description="What the tool does")
    language: Literal["python", "tcl"] = Field(description="Programming language (python or tcl)")
    parameters: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Parameter specifications: {param_name: {type, description, default}}"
    )
    return_type: str = Field(default="Dict[str, Any]", description="Return type specification")
    dependencies: List[str] = Field(default_factory=list, description="Required imports/modules")
    purpose: str = Field(description="Detailed purpose and use case")
    examples: Optional[str] = Field(default=None, description="Usage examples")


class ScriptTemplate(BaseModel):
    """Template for script generation"""
    template_type: Literal["mdp", "analysis", "slurm", "preprocessing", "tcl"] = Field(
        description="Type of script template"
    )
    name: str = Field(description="Script name")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Template parameters")
    context: Dict[str, Any] = Field(default_factory=dict, description="Context for generation")


# ========== Result Schemas ==========

class GeneratedTool(BaseModel):
    """Information about a generated tool"""
    name: str = Field(description="Tool name")
    file_path: str = Field(description="Path to generated file")
    language: str = Field(description="Programming language")
    function_signature: str = Field(default="", description="Function signature")
    imports: List[str] = Field(default_factory=list, description="Required imports")
    status: Literal["generated", "validated", "failed"] = Field(description="Generation status")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings")


class ToolValidationResult(BaseModel):
    """Result of tool validation"""
    success: bool = Field(description="Whether validation passed")
    tool_name: str = Field(description="Name of validated tool")
    syntax_valid: bool = Field(default=False, description="Python/TCL syntax is valid")
    imports_valid: bool = Field(default=False, description="All imports are available")
    signature_valid: bool = Field(default=False, description="Function signature is correct")
    issues: List[str] = Field(default_factory=list, description="Issues found")
    recommendations: List[str] = Field(default_factory=list, description="Improvement suggestions")


class ProgrammerResult(BaseModel):
    """Result of programmer execution"""
    success: bool = Field(description="Whether all tools were created successfully")
    generated_tools: List[GeneratedTool] = Field(
        default_factory=list,
        description="List of generated tools"
    )
    failed_tools: List[str] = Field(default_factory=list, description="Tools that failed")
    output_directory: str = Field(description="Directory containing generated code")
    report: str = Field(description="Detailed execution report")
    tools_available: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of tool names to file paths"
    )
    validation_results: Dict[str, ToolValidationResult] = Field(
        default_factory=dict,
        description="Validation results for each tool"
    )
    issues: List[str] = Field(default_factory=list, description="Issues encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings")


# ========== Planning Schemas ==========

class ProgrammerStep(BaseModel):
    """Single step in programmer execution plan"""
    name: str = Field(description="Step name")
    description: str = Field(description="What this step does")
    tool_name: str = Field(description="Tool to invoke (from programmer tools)")
    tool_params: Dict[str, Any] = Field(default_factory=dict, description="Parameters for tool")
    reason: str = Field(description="Why this step is needed")
    dependencies: List[str] = Field(default_factory=list, description="Steps that must complete first")


class ProgrammerPlan(BaseModel):
    """Plan for creating multiple tools"""
    reasoning: str = Field(description="Why these tools are needed")
    overview: str = Field(description="High-level summary of the plan")
    steps: List[ProgrammerStep] = Field(description="Ordered steps to execute")
    tools_to_create: List[ToolSpecification] = Field(
        default_factory=list,
        description="List of tools to generate"
    )
    estimated_complexity: Literal["low", "medium", "high"] = Field(
        description="Complexity estimate"
    )
    potential_issues: List[str] = Field(default_factory=list, description="Potential problems")
    recommendations: List[str] = Field(default_factory=list, description="Recommendations")


# ========== Agent I/O Schemas ==========

class ProgrammerAgentInput(BaseModel):
    """Input to programmer agent from planner"""
    working_directory: str = Field(description="Working directory for generated code")
    planner_instructions: str = Field(description="Instructions from planner")
    tool_specifications: Optional[List[ToolSpecification]] = Field(
        default=None,
        description="Specifications for tools to create"
    )
    user_goal: Optional[str] = Field(default=None, description="Original user goal")
    context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Workflow context (state, plan, etc.)"
    )
    force_field: str = Field(default="amber99sb-ildn", description="Force field being used")
    md_engine: str = Field(default="gromacs", description="MD engine (gromacs, amber, etc.)")
    output_subdirs: Optional[Dict[str, str]] = Field(
        default=None,
        description="Specific output subdirectories (python, tcl, mdp, etc.)"
    )


class ProgrammerAgentOutput(BaseModel):
    """Output from programmer agent"""
    success: bool = Field(description="Whether programmer succeeded")
    result: ProgrammerResult = Field(description="Detailed results")
    next_actions: List[str] = Field(
        default_factory=list,
        description="Recommended next steps"
    )
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    topology_file: Optional[str] = Field(None, description="Generated topology if any")
    coordinates: Optional[str] = Field(None, description="Generated coordinates if any")


# ========== Execution Result Schemas ==========

class ProgrammerExecutionResult(BaseModel):
    """Result of executing programmer plan"""
    success: bool = Field(description="Whether execution succeeded")
    completed_steps: int = Field(description="Number of steps completed")
    total_steps: int = Field(description="Total number of steps in plan")
    issues: List[str] = Field(default_factory=list, description="Issues encountered")
    warnings: List[str] = Field(default_factory=list, description="Warnings")
    report: str = Field(description="Execution report")
    generated_files: Dict[str, str] = Field(
        default_factory=dict,
        description="Map of file types to paths"
    )
    step_results: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Results from each step"
    )

