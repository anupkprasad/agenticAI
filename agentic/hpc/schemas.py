"""
Pydantic schemas for HPC job submission and monitoring.

Note: Tool-level input validation is handled automatically by LangChain's @tool decorator.
This file only contains workflow orchestration schemas for agent-level coordination.
Time estimation is handled by src/hpc/time_estimator.py.
"""
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field, validator


class HPCConfig(BaseModel):
    """HPC system configuration - used by workflow orchestration"""
    partition: str = Field(default="gpu_p", description="SLURM partition name")
    nodes: int = Field(default=1, description="Number of compute nodes")
    ntasks: int = Field(default=1, description="Number of tasks")
    cpus_per_task: int = Field(default=64, description="CPUs per task")
    memory: str = Field(default="40G", description="Memory allocation")
    gpu_count: int = Field(default=1, description="Number of GPUs")
    time_limit: str = Field(default="3-00:00:00", description="Time limit (days-hours:min:sec)")
    email: Optional[str] = Field(None, description="Email for notifications")
    gromacs_module: str = Field(
        default="GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2",
        description="GROMACS module to load"
    )
    
    @validator("cpus_per_task")
    def validate_cpus(cls, v):
        if v < 1 or v > 256:
            raise ValueError("CPUs per task must be between 1 and 256")
        return v
    
    @validator("gpu_count")
    def validate_gpus(cls, v):
        if v < 0 or v > 8:
            raise ValueError("GPU count must be between 0 and 8")
        return v


class HPCJobStatus(BaseModel):
    """HPC job status information"""
    job_id: str = Field(..., description="Job ID")
    status: Literal["PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "TIMEOUT", "UNKNOWN"] = Field(
        ..., description="Job status"
    )
    elapsed_time: Optional[str] = Field(None, description="Elapsed time")
    remaining_time: Optional[str] = Field(None, description="Estimated remaining time")
    node_list: Optional[str] = Field(None, description="Allocated nodes")


class HPCExecutionPlan(BaseModel):
    """Complete HPC execution plan"""
    reasoning: str = Field(..., description="Reasoning for the execution plan")
    overview: str = Field(..., description="High-level overview of the plan")
    steps: List[Dict[str, Any]] = Field(..., description="Ordered list of execution steps")
    potential_issues: List[str] = Field(default=[], description="Potential issues to watch for")
    recommendations: List[str] = Field(default=[], description="Recommendations for execution")
    estimated_time: Optional[str] = Field(None, description="Estimated total execution time")
