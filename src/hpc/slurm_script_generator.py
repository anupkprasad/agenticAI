"""
SLURM Job Script Generator for GROMACS Simulations

Generates SLURM submission scripts for HPC systems running GROMACS MD simulations.
Includes all simulation phases: minimization, NVT, NPT, and production MD.
"""
import os
from pathlib import Path
from typing import Dict, Any, Optional, List
from langchain.tools import tool


@tool
def generate_slurm_script(
    job_name: str,
    working_dir: str,
    topology_file: str = "topol.top",
    input_structure: str = "system.gro",
    simulation_phases: Optional[List[str]] = None,
    partition: str = "gpu_p",
    nodes: int = 1,
    ntasks: int = 1,
    cpus_per_task: int = 64,
    memory: str = "40G",
    time_limit: str = "5-00:00:00",
    gpu_count: int = 1,
    email: Optional[str] = None,
    gromacs_module: str = "GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2",
    output_script: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate SLURM job submission script for GROMACS MD simulation on HPC systems.
    
    Creates a complete SLURM script that runs all simulation phases:
    1. Energy minimization (minim.mdp)
    2. NVT equilibration (nvt.mdp)
    3. NPT equilibration (npt.mdp)
    4. Production MD (md.mdp)
    
    Args:
        job_name: SLURM job name (e.g., "protein_md", "atp_complex")
        working_dir: Directory containing topology, coordinate, and MDP files
        topology_file: Topology file name (default: topol.top)
        input_structure: Starting coordinate file (default: system.gro)
        simulation_phases: List of phases to run (default: ["minim", "nvt", "npt", "md"])
        partition: SLURM partition name (default: gpu_p)
        nodes: Number of compute nodes (default: 1)
        ntasks: Number of tasks/processes (default: 1)
        cpus_per_task: CPU cores per task (default: 64)
        memory: Memory allocation (default: 40G)
        time_limit: Time limit in format days-hours:minutes:seconds (default: 5-00:00:00)
        gpu_count: Number of GPUs to request (default: 1)
        email: Email address for job notifications (optional)
        gromacs_module: GROMACS module name to load (default: GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2)
        output_script: Output script path (default: <job_name>_run.sh in working_dir)
        
    Returns:
        Dict with success status, script path, and configuration summary
        
    Example:
        >>> generate_slurm_script(
        ...     job_name="protein_md",
        ...     working_dir="working_dir/simsetup",
        ...     email="user@university.edu",
        ...     time_limit="2-00:00:00"  # 2 days
        ... )
    """
    try:
        # Default simulation phases
        if simulation_phases is None:
            simulation_phases = ["minim", "nvt", "npt", "md"]

        # Validate working directory and convert to absolute path
        work_path = Path(working_dir).resolve()

        if (work_path / "minim2.mdp").is_file() and "minim2" not in simulation_phases:
            simulation_phases = ["minim", "minim2"] + [
                p for p in simulation_phases if p != "minim"
            ]
        if not work_path.exists():
            return {
                "success": False,
                "error": f"Working directory does not exist: {working_dir}"
            }
        
        # Use absolute path for all operations
        working_dir_abs = str(work_path)
        
        # Determine output script path
        if output_script is None:
            output_script = str(work_path / f"{job_name}_run.sh")
        
        # Build SLURM header
        slurm_header = f"""#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --nodes={nodes}
#SBATCH --ntasks={ntasks}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --mem={memory}
#SBATCH --time={time_limit}
#SBATCH --output=%x_%j.out
#SBATCH --gres=gpu:{gpu_count}
"""
        
        # Add email notifications if provided
        if email:
            slurm_header += f"""#SBATCH --mail-user={email}
#SBATCH --mail-type=END,FAIL
"""
        
        # Module loading section
        module_section = f"""
# Load GROMACS module
module load {gromacs_module}
source $EBROOTGROMACS/bin/GMXRC

# Print environment information
echo "======================================"
echo "Job: {job_name}"
echo "Started: $(date)"
echo "Host: $(hostname)"
echo "Working Directory: $(pwd)"
echo "GROMACS Version: $(gmx --version | head -1)"
echo "======================================"
"""
        
        # Change to working directory (use absolute path)
        execution_section = f"""
# Change to working directory
cd {working_dir_abs} || exit 1
echo "Changed to directory: $(pwd)"

# MPI foss GROMACS builds may auto-start multiple ranks under SLURM, which fails
# domain decomposition on modest boxes. Force one MPI rank + OpenMP threads.
export OMP_PLACES=cores
OMP_CPU_THREADS=${{SLURM_CPUS_PER_TASK:-{cpus_per_task}}}
OMP_GPU_THREADS=${{SLURM_CPUS_PER_TASK:-{cpus_per_task}}}
if [ "$OMP_GPU_THREADS" -gt 16 ]; then OMP_GPU_THREADS=16; fi
# OMP_NUM_THREADS must match -ntomp on each mdrun line (set per phase below).
MDRUN_CPU="-ntmpi 1 -ntomp ${{OMP_CPU_THREADS}} -nb cpu -pme cpu -bonded cpu"
MDRUN_GPU="-ntmpi 1 -ntomp ${{OMP_GPU_THREADS}} -nb gpu -pme gpu -bonded cpu -update cpu"
"""
        
        # Build GROMACS command sections for each phase
        gromacs_commands = []
        
        phase_descriptions = {
            "minim": "Energy Minimization (stage 1, restrained)",
            "minim2": "Energy Minimization (stage 2, unrestrained)",
            "nvt": "NVT Equilibration (Constant Volume)",
            "npt": "NPT Equilibration (Constant Pressure)",
            "md": "Production MD Simulation"
        }
        
        # Track input/output files across phases
        prev_output = input_structure
        
        for i, phase in enumerate(simulation_phases):
            desc = phase_descriptions.get(phase, phase.upper())
            
            # File names
            mdp_file = f"{phase}.mdp"
            tpr_file = f"{phase}.tpr"
            output_prefix = phase
            
            # Determine input coordinate file
            if i == 0:
                input_coord = input_structure
                ref_coord = input_structure  # For position restraints
            else:
                prev_phase = simulation_phases[i-1]
                input_coord = f"{prev_phase}.gro"
                ref_coord = f"{prev_phase}.gro"
            
            # Build grompp command
            grompp_cmd = f"""
# ===== {desc} =====
echo ""
echo "Starting {desc}..."
echo "Input: {input_coord}, MDP: {mdp_file}"

# Prepare TPR file
gmx grompp -f {mdp_file} \\
           -c {input_coord} \\
           -r {ref_coord} \\
           -p {topology_file} \\
           -o {tpr_file} \\
           -maxwarn 3

if [ $? -ne 0 ]; then
    echo "ERROR: grompp failed for {phase}"
    exit 1
fi
"""
            
            # minim: CPU thread-parallel; equilibration/production: GPU when requested
            if gpu_count > 0 and phase in ("nvt", "npt", "md"):
                mdrun_line = (
                    f"export OMP_NUM_THREADS=${{OMP_GPU_THREADS}}\n"
                    f"gmx mdrun -v -deffnm {output_prefix} $MDRUN_GPU"
                )
            else:
                mdrun_line = (
                    f"export OMP_NUM_THREADS=${{OMP_CPU_THREADS}}\n"
                    f"gmx mdrun -v -deffnm {output_prefix} $MDRUN_CPU"
                )

            mdrun_cmd = f"""
# Run simulation
{mdrun_line}

if [ $? -ne 0 ]; then
    echo "ERROR: mdrun failed for {phase}"
    exit 1
fi

echo "{desc} completed successfully"
"""
            
            gromacs_commands.append(grompp_cmd + mdrun_cmd)
        
        # Final section
        final_section = """
# ===== Job Completion =====
echo ""
echo "======================================"
echo "All simulation phases completed!"
echo "Finished: $(date)"
echo "======================================"

# List output files
echo ""
echo "Generated files:"
ls -lh *.gro *.xtc *.edr *.log 2>/dev/null || echo "No output files found"
"""
        
        # Combine all sections
        script_content = (
            slurm_header +
            module_section +
            execution_section +
            "\n".join(gromacs_commands) +
            final_section
        )
        
        # Write script file
        with open(output_script, 'w') as f:
            f.write(script_content)
        
        # Make executable
        os.chmod(output_script, 0o755)
        
        return {
            "success": True,
            "script_path": output_script,
            "job_name": job_name,
            "phases": simulation_phases,
            "configuration": {
                "partition": partition,
                "nodes": nodes,
                "cpus_per_task": cpus_per_task,
                "memory": memory,
                "time_limit": time_limit,
                "gpu_count": gpu_count,
                "gromacs_module": gromacs_module
            },
            "message": f"SLURM script generated: {output_script}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Script generation failed: {e}"
        }


@tool
def generate_simple_slurm_script(
    job_name: str,
    working_dir: str,
    commands: List[str],
    partition: str = "gpu_p",
    cpus_per_task: int = 64,
    memory: str = "40G",
    time_limit: str = "5-00:00:00",
    gpu_count: int = 1,
    email: Optional[str] = None,
    modules: Optional[List[str]] = None,
    output_script: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate a simple SLURM script for custom commands (not specifically GROMACS).
    
    Args:
        job_name: SLURM job name
        working_dir: Working directory for job execution
        commands: List of shell commands to execute
        partition: SLURM partition (default: gpu_p)
        cpus_per_task: CPU cores (default: 64)
        memory: Memory allocation (default: 40G)
        time_limit: Time limit (default: 5-00:00:00)
        gpu_count: Number of GPUs (default: 1)
        email: Email for notifications (optional)
        modules: List of modules to load (optional)
        output_script: Output script path (default: <job_name>.sh in working_dir)
        
    Returns:
        Dict with success status and script path
    """
    try:
        work_path = Path(working_dir)
        work_path.mkdir(parents=True, exist_ok=True)
        
        if output_script is None:
            output_script = str(work_path / f"{job_name}.sh")
        
        # Build SLURM header
        script = f"""#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --partition={partition}
#SBATCH --cpus-per-task={cpus_per_task}
#SBATCH --mem={memory}
#SBATCH --time={time_limit}
#SBATCH --output=%x_%j.out
#SBATCH --gres=gpu:{gpu_count}
"""
        
        if email:
            script += f"""#SBATCH --mail-user={email}
#SBATCH --mail-type=END,FAIL
"""
        
        # Module loading
        if modules:
            script += "\n# Load modules\n"
            for module in modules:
                script += f"module load {module}\n"
        
        # Change to working directory
        script += f"""
# Change to working directory
cd {working_dir} || exit 1

# Execute commands
"""
        
        # Add user commands
        for cmd in commands:
            script += f"{cmd}\n"
        
        # Write and make executable
        with open(output_script, 'w') as f:
            f.write(script)
        os.chmod(output_script, 0o755)
        
        return {
            "success": True,
            "script_path": output_script,
            "message": f"SLURM script generated: {output_script}"
        }
        
    except Exception as e:
        return {
            "success": False,
            "error": f"Script generation failed: {e}"
        }
