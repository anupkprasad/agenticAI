#!/bin/bash
#SBATCH --job-name=q8nb16
#SBATCH --partition=gpu_p
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=64
#SBATCH --mem=40G
#SBATCH --time=5-00:00:00
#SBATCH --output=%x_%j.out
#SBATCH --gres=gpu:1
#SBATCH --exclude=ra7-6

# Load GROMACS module
module load GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2
source $EBROOTGROMACS/bin/GMXRC

# Print environment information
echo "======================================"
echo "Job: q8nb16"
echo "Started: $(date)"
echo "Host: $(hostname)"
echo "Working Directory: $(pwd)"
echo "GROMACS Version: $(gmx --version | head -1)"
echo "======================================"

# Change to working directory
cd /home/akp66103/workspace/agenticAI/example/pseudo_apo_holo/q8nb16/hpc || exit 1
echo "Changed to directory: $(pwd)"

# MPI foss GROMACS builds may auto-start multiple ranks under SLURM, which fails
# domain decomposition on modest boxes. Force one MPI rank + OpenMP threads.
export OMP_PLACES=cores
OMP_CPU_THREADS=${SLURM_CPUS_PER_TASK:-64}
OMP_GPU_THREADS=${SLURM_CPUS_PER_TASK:-64}
if [ "$OMP_GPU_THREADS" -gt 16 ]; then OMP_GPU_THREADS=16; fi
# OMP_NUM_THREADS must match -ntomp on each mdrun line (set per phase below).
MDRUN_CPU="-ntmpi 1 -ntomp ${OMP_CPU_THREADS} -nb cpu -pme cpu -bonded cpu"
MDRUN_GPU="-ntmpi 1 -ntomp ${OMP_GPU_THREADS} -nb gpu -pme gpu -bonded cpu -update cpu"

# ===== Energy Minimization (stage 1, restrained) =====
echo ""
echo "Starting Energy Minimization (stage 1, restrained)..."
echo "Input: system.gro, MDP: minim.mdp"

# Prepare TPR file
gmx grompp -f minim.mdp \
           -c system.gro \
           -r system.gro \
           -p topol.top \
           -o minim.tpr \
           -maxwarn 3

if [ $? -ne 0 ]; then
    echo "ERROR: grompp failed for minim"
    exit 1
fi

# Run simulation
export OMP_NUM_THREADS=${OMP_CPU_THREADS}
gmx mdrun -v -deffnm minim $MDRUN_CPU

if [ $? -ne 0 ]; then
    echo "ERROR: mdrun failed for minim"
    exit 1
fi

echo "Energy Minimization (stage 1, restrained) completed successfully"


# ===== NVT Equilibration (Constant Volume) =====
echo ""
echo "Starting NVT Equilibration (Constant Volume)..."
echo "Input: minim.gro, MDP: nvt.mdp"

# Prepare TPR file
gmx grompp -f nvt.mdp \
           -c minim.gro \
           -r minim.gro \
           -p topol.top \
           -o nvt.tpr \
           -maxwarn 3

if [ $? -ne 0 ]; then
    echo "ERROR: grompp failed for nvt"
    exit 1
fi

# Run simulation
export OMP_NUM_THREADS=${OMP_GPU_THREADS}
gmx mdrun -v -deffnm nvt $MDRUN_GPU

if [ $? -ne 0 ]; then
    echo "ERROR: mdrun failed for nvt"
    exit 1
fi

echo "NVT Equilibration (Constant Volume) completed successfully"


# ===== NPT Equilibration (Constant Pressure) =====
echo ""
echo "Starting NPT Equilibration (Constant Pressure)..."
echo "Input: nvt.gro, MDP: npt.mdp"

# Prepare TPR file
gmx grompp -f npt.mdp \
           -c nvt.gro \
           -r nvt.gro \
           -p topol.top \
           -o npt.tpr \
           -maxwarn 3

if [ $? -ne 0 ]; then
    echo "ERROR: grompp failed for npt"
    exit 1
fi

# Run simulation
export OMP_NUM_THREADS=${OMP_GPU_THREADS}
gmx mdrun -v -deffnm npt $MDRUN_GPU

if [ $? -ne 0 ]; then
    echo "ERROR: mdrun failed for npt"
    exit 1
fi

echo "NPT Equilibration (Constant Pressure) completed successfully"


# ===== Production MD Simulation =====
echo ""
echo "Starting Production MD Simulation..."
echo "Input: npt.gro, MDP: md.mdp"

# Prepare TPR file
gmx grompp -f md.mdp \
           -c npt.gro \
           -r npt.gro \
           -p topol.top \
           -o md.tpr \
           -maxwarn 3

if [ $? -ne 0 ]; then
    echo "ERROR: grompp failed for md"
    exit 1
fi

# Run simulation
export OMP_NUM_THREADS=${OMP_GPU_THREADS}
gmx mdrun -v -deffnm md $MDRUN_GPU

if [ $? -ne 0 ]; then
    echo "ERROR: mdrun failed for md"
    exit 1
fi

echo "Production MD Simulation completed successfully"

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
