#!/bin/bash
#SBATCH --job-name=ollama        # Job name
#SBATCH --partition=kannan_p               # --partition=kannan_p, gpu_p   GPU partition (adjust if needed)
#SBATCH --nodes=1                       # Use 1 node
#SBATCH --ntasks=1                      # Single task
#SBATCH --cpus-per-task=64              # CPU threads per task
#SBATCH --mem=200G                      # Memory per node
#SBATCH --time=7-0:00:00               # Max runtime: 3 days
#SBATCH --gres=gpu:1                     # Number of GPUs
#SBATCH --mail-user=akp66103@uga.edu     # Email notifications
#SBATCH --mail-type=END,FAIL             # Notify on job END or FAIL
#SBATCH --output=server.log              # Output log

# Load any required modules (if needed for Singularity / CUDA)
##module load singularity/3.11.2
module load CUDA/12.8.0   # adjust to your HPC available version

# Set environment variables for Ollama (optional but recommended)
export OLLAMA_MODELS=/home/akp66103/ollama_models
export OLLAMA_CACHE=/home/akp66103/ollama_cache
export OLLAMA_NUM_THREADS=64
export OLLAMA_CONTEXT_LENGTH=4096
export OLLAMA_FLASH_ATTENTION=true
# Concurrent LLM requests (match --llm-concurrency / AGENTIC_LLM_CONCURRENCY default).
export OLLAMA_NUM_PARALLEL=4
export OLLAMA_MAX_QUEUE=512
export OLLAMA_KEEP_ALIVE=-1

# Launch Ollama server in background
nohup singularity exec --nv --cleanenv \
  -B $HOME/ollama_models:/ollama \
  -B $HOME/ollama_cache:/root/.cache \
  ~/containers/ollama_cuda.sif \
  ollama serve

# Give server a few seconds to initialize
sleep 30

# Optional: test that server is running
singularity exec --nv --cleanenv \
  -B $HOME/ollama_models:/ollama \
  ~/containers/ollama_cuda.sif \
  ollama ps

echo "You can now connect and run models."



################ 
###  To list of available models, run the following command after the server is up:
# singularity exec --nv --cleanenv \
#   -B $HOME/ollama_models:/ollama \
#   ~/containers/ollama_cuda.sif \
#   ollama list

### TO install a model, run the following command:
# singularity exec --nv --cleanenv \
#   -B $HOME/ollama_models:/ollama \
#   ~/containers/ollama_cuda.sif \
#   ollama pull <model_name>