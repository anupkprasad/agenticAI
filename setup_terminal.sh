#!/bin/bash
# GPU Terminal Setup Script - Connect to Ollama Server Node
# Usage: ./setup_terminal.sh [JOB_ID]
# Example: ./setup_terminal.sh 42358496

# Auto-detect Ollama job if no argument provided
if [ -z "$1" ]; then
    JOB_ID=$(squeue --me --noheader --format="%i %j" | grep -i "ollama" | head -1 | awk '{print $1}')
    if [ -z "$JOB_ID" ]; then
        echo "❌ No Ollama job found. Please provide job ID:"
        echo "Usage: ./setup_terminal.sh [JOB_ID]"
        echo ""
        echo "Your running jobs:"
        squeue --me --format="%.18i %.30j %.8T %R"
        exit 1
    fi
    echo "🔍 Auto-detected Ollama job: $JOB_ID"
else
    JOB_ID=$1
fi

echo "🚀 Connecting to GPU node with Ollama server..."
echo "📍 Job ID: $JOB_ID"
echo "⏳ Please wait for connection..."
echo ""

# Get the actual node from the running job
NODE=$(squeue --noheader --format=%N --jobs=$JOB_ID 2>/dev/null | head -1)

if [ -z "$NODE" ]; then
    echo "❌ Error: Could not find node for job $JOB_ID"
    echo "💡 Check your job ID with: sq --me"
    exit 1
fi

echo "✅ Node found: $NODE"
echo ""
echo "💡 Auto-activating conda environment in 3 seconds..."
echo "💡 Then you can run: python llm_chat.py"
echo ""

# Use srun with --overlap to avoid resource conflicts
# This is SLURM-native and more reliable than SSH
# Auto-activate conda environment after connection
srun --overlap --jobid=$JOB_ID --pty bash -c "
    echo '⏳ Waiting 3 seconds for node connection...'
    sleep 3
    echo '🔧 Activating conda environment...'
    source ~/conda_envs/ollama_env/bin/activate || conda activate ~/conda_envs/ollama_env/
    echo '✅ Conda environment activated: ollama_env'
    echo '💡 You can now run: python llm_chat.py'
    echo ''
    exec bash
"