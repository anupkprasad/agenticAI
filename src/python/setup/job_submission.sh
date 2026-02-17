#!/bin/bash
#SBATCH --job-name=eq_q7z               # Job name (testBowtie2)
#SBATCH --partition=gpu_p               # Partition name (batch, highmem_p, or gpu_p)
#SBATCH --nodes=1                       # Number of compute nodes for resources to be spread out over (increase only if using MPI enabled software)
#SBATCH --ntasks=1                      # 1 task (process) for below commands
#SBATCH --cpus-per-task=64              # CPU core count per task, by default 1 CPU core per task
#SBATCH --mem=40G                       # Memory per node (4GB); by default using M as unit
#SBATCH --time=0-10:00:00               # Time limit hrs:min:sec or days-hours:minutes:seconds
##SBATCH --output=%x_%j.out             # Standard output log, e.g., testBowtie2_12345.out
#SBATCH --mail-user=akp66103@uga.edu    # Where to send mail
#SBATCH --mail-type=END,FAIL            # Mail events (BEGIN, END, FAIL, ALL)
#SBATCH --gres=gpu:1               #GPU being used

module load GROMACS/2024.4-foss-2023b-CUDA-12.4.0-PLUMED-2.9.2
source $EBROOTGROMACS/bin/GMXRC


# Preprocessing for energy minimization
gmx grompp -f ./mdp/min.mdp -c pdb_ion.gro -r pdb_ion.gro -p topol.top -o min.tpr -maxwarn 3
gmx mdrun -v -deffnm min

gmx grompp -p topol.top -c min.gro -r min.gro -o nvt.tpr -f ./mdp/nvt.mdp
gmx mdrun -v -deffnm nvt

gmx grompp -p topol.top -c nvt.gro -r nvt.gro -t nvt.cpt -o npt.tpr -f ./mdp/npt.mdp -maxwarn 1
gmx mdrun -v -deffnm npt

gmx grompp -p topol.top -c npt.gro -r npt.gro -t npt.cpt -o md.tpr -f ./mdp/md.mdp -maxwarn 1

# check the system
echo 0 | gmx trjconv -f npt.gro -s md.tpr -o system.pdb -dump 0

