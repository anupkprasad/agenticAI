"""
Pydantic schemas for HPC job submission and monitoring
"""
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field, validator


class HPCConfig(BaseModel):
    """HPC system configuration"""
    partition: str = Field(default="gpu_p", description="SLURM partition name")
    nodes: int = Field(default=1, description="Number of compute nodes")
    ntasks: int = Field(default=1, description="Number of tasks")
    cpus_per_task: int = Field(default=64, description="CPUs per task")
    memory: str = Field(default="40G", description="Memory allocation")
    gpu_count: int = Field(default=1, description="Number of GPUs")
    time_limit: str = Field(default="0-10:00:00", description="Time limit (days-hours:min:sec)")
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


class JobSubmissionInput(BaseModel):
    """Input for job submission"""
    job_name: str = Field(..., description="Job name")
    working_dir: str = Field(..., description="Working directory with simulation files")
    topology_file: str = Field(default="topol.top", description="Topology file")
    input_structure: str = Field(default="system.gro", description="Input coordinate file")
    simulation_phases: List[str] = Field(
        default=["minim", "nvt", "npt", "md"],
        description="Simulation phases to run"
    )
    hpc_config: Optional[HPCConfig] = Field(None, description="HPC configuration")
    output_script: Optional[str] = Field(None, description="Output script path")


class JobMonitoringInput(BaseModel):
    """Input for job monitoring"""
    job_id: str = Field(..., description="SLURM job ID")
    check_interval: int = Field(default=3600, description="Check interval in seconds (default: 1 hour)")
    max_checks: int = Field(default=48, description="Maximum number of status checks")
    
    @validator("check_interval")
    def validate_interval(cls, v):
        if v < 60:  # Minimum 1 minute
            raise ValueError("Check interval must be at least 60 seconds")
        return v


class DataDownloadInput(BaseModel):
    """Input for data download from HPC"""
    remote_dir: str = Field(..., description="Remote directory path")
    local_dir: str = Field(..., description="Local download directory")
    file_patterns: List[str] = Field(
        default=["*.xtc", "*.gro", "*.edr", "*.log", "*.cpt"],
        description="File patterns to download"
    )
    include_subdirs: bool = Field(default=False, description="Include subdirectories")


class FileCopyInput(BaseModel):
    """Input for copying files to HPC working directory"""
    source_dir: str = Field(..., description="Source directory (e.g., working_dir/simsetup)")
    dest_dir: str = Field(..., description="Destination directory (e.g., working_dir/hpc)")
    file_patterns: List[str] = Field(
        default=["*.gro", "*.top", "*.mdp", "*.itp"],
        description="File patterns to copy"
    )
    create_dest: bool = Field(default=True, description="Create destination if doesn't exist")


class SimulationTimeEstimate(BaseModel):
    """Estimate simulation time requirements"""
    production_ns: float = Field(default=10.0, description="Production simulation length (ns)")
    timestep_ps: float = Field(default=0.002, description="Integration timestep (ps)")
    frame_interval_ps: float = Field(default=10.0, description="Frame output interval (ps)")
    system_size: int = Field(default=50000, description="Number of atoms")
    
    @validator("production_ns")
    def validate_production(cls, v):
        if v <= 0:
            raise ValueError("Production time must be positive")
        return v
    
    def calculate_steps(self) -> int:
        """Calculate total number of MD steps"""
        return int(self.production_ns * 1000 / self.timestep_ps)
    
    def estimate_walltime_hours(self) -> float:
        """
        Estimate walltime in hours based on system size and GPU performance.
        Rule of thumb: ~1 ns/day for 50k atoms on modern GPU
        """
        # Base performance: 1 ns/day (24 hours) for 50k atoms
        base_performance_ns_per_hour = 1.0 / 24.0
        
        # Scale by system size (roughly linear)
        size_factor = self.system_size / 50000.0
        
        # Estimate production time
        production_hours = self.production_ns / base_performance_ns_per_hour * size_factor
        
        # Add equilibration time (typically 10-20% of production)
        equilibration_hours = production_hours * 0.15
        
        # Add buffer for minimization and overhead (10%)
        total_hours = (production_hours + equilibration_hours) * 1.1
        
        return total_hours
    
    def format_slurm_time(self) -> str:
        """Format estimated time as SLURM time limit (days-hours:min:sec)"""
        total_hours = self.estimate_walltime_hours()
        days = int(total_hours // 24)
        hours = int(total_hours % 24)
        minutes = int((total_hours % 1) * 60)
        return f"{days}-{hours:02d}:{minutes:02d}:00"


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
