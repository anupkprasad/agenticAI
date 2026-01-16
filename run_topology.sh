#!/bin/bash
# ATP topology generation script for interactive compute session

echo "Initializing conda..."
eval "$(conda shell.bash hook)"
conda activate ~/conda_envs/ollama_env/

echo "Changing to working directory..."
cd working_dir

echo "Setting library path..."
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib:$LD_LIBRARY_PATH"

echo "Running topology generator..."
python ligand_topology_generator.py ATP.pdb ATP -4

echo "Topology generation completed!"
