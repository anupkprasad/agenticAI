#!/bin/bash

# Variables
gro_name="complex.gro"
pad=1.2
ion_conc=0.15
pos_ion="NA"
neg_ion="CL"


# Prepare equilibration directory
cp "$gro_name" ./equilibration/
cp "topol.top" ./equilibration/
cp -r ./amber99sb-ildn.ff ./equilibration/
cp "posre.itp" ./equilibration/
cd ./equilibration || exit 1
cp -r ~/myScripts/simulations/gmx/simulationSetup/mdp_lig/mdp ./
cp ~/myScripts/simulations/gmx/simulationSetup/equil.sh ./


#### job_name for HPC
JN=$(pwd | sed -n 's/.*atp_\([^_]*\)_kd.*/\1/p')
sed -i "s/^#SBATCH --job-name=eq_.*$/#SBATCH --job-name=eq_${JN}\t\t# Job name/" equil.sh

### solvation and system setup
gmx editconf -f "$gro_name" -o boxed.gro -d "$pad" -bt cubic
gmx solvate -cp boxed.gro -p topol.top -o pdb_solv.gro

gmx grompp -f ./mdp/min.mdp -c pdb_solv.gro -r pdb_solv.gro -p topol.top -o ion.tpr -maxwarn 3

# Ion addition with custom ion names
echo SOL | gmx genion -s ion.tpr -o pdb_ion.gro -p topol.top -conc "$ion_conc" -neutral -pname "$pos_ion" -nname "$neg_ion"

# Preprocessing for energy minimization
gmx grompp -f ./mdp/min.mdp -c pdb_ion.gro -r pdb_ion.gro -p topol.top -o min.tpr -maxwarn 3

# source /home/anup/workspace/project1/env-md/bin/activate
# python /home/anup/myScripts/simulations/createTopology.py topol.top pdb_ion.gro
# deactivate