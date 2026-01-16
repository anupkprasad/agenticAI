#!/bin/bash
# Submit topology generation as a batch job
#SBATCH --job-name=atp_topology
#SBATCH --time=00:30:00
#SBATCH --ntasks=1
#SBATCH --mem=4G

# Activate conda environment
conda activate ~/conda_envs/ollama_env/

# Navigate to working directory
cd /home/akp66103/workspace/agenticAI/working_dir

# Set library path
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"

# Run topology generator
python ligand_topology_generator.py ATP.pdb ATP -4
