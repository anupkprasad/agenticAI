"""
HPC SLURM Script Creator - Wrapper for SLURM script generation
"""
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from langchain.tools import tool

logger = logging.getLogger(__name__)


@tool
def create_slurm_script(
    job_name: str,
    working_dir: str,
    topology_file: str = "topol.top",
    input_structure: str = "system.gro",
    simulation_phases: Optional[List[str]] = None,
    partition: str = "gpu_p",
    cpus_per_task: int = 64,
    memory: str = "40G",
    time_limit: str = "3-00:00:00",
    gpu_count: int = 1,
    email: Optional[str] = None,
    gromacs_module: str = "GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2"
) -> Dict[str, Any]:
    """
    Create SLURM job submission script for GROMACS simulation.
    
    Args:
        job_name: Job name for SLURM
        working_dir: Directory containing simulation files
        topology_file: Topology file name
        input_structure: Input coordinate file name
        simulation_phases: List of phases (default: ["minim", "nvt", "npt", "md"])
        partition: SLURM partition
        cpus_per_task: CPU cores per task
        memory: Memory allocation (e.g., "40G")
        time_limit: Time limit (days-hours:min:sec)
        gpu_count: Number of GPUs
        email: Email for notifications
        gromacs_module: GROMACS module to load
        
    Returns:
        Dict with script path and configuration
    """
    try:
        # Import and invoke the tool from slurm_script_generator
        from src.hpc.slurm_script_generator import generate_slurm_script as gen_tool
        
        # Use the tool's invoke method
        result = gen_tool.invoke({
            "job_name": job_name,
            "working_dir": working_dir,
            "topology_file": topology_file,
            "input_structure": input_structure,
            "simulation_phases": simulation_phases,
            "partition": partition,
            "cpus_per_task": cpus_per_task,
            "memory": memory,
            "time_limit": time_limit,
            "gpu_count": gpu_count,
            "email": email,
            "gromacs_module": gromacs_module
        })
        
        return result
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Script creation failed: {e}"
        }
