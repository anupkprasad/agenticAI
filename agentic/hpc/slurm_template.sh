#!/bin/bash
## Example SLURM job template for MD runs
#SBATCH --job-name=md_run
#SBATCH --time=02:00:00
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=16
#SBATCH --partition=compute

echo "Starting job for {{PDB}}"
# Load modules here, e.g. module load gromacs
# Run your MD engine here, e.g. gmx mdrun -s topol.tpr -deffnm run
