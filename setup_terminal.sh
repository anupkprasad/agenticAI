#!/bin/bash
# GPU Terminal Setup Script - Simple Version
# Usage: ./setup_terminal.sh

echo "🚀 Step 1: Connecting to GPU node..."
echo "📍 Target: ra8-7 (job ID: 42162557), check with: sq --me if it is changed"
echo "⏳ Please wait for connection..."
echo ""

echo "💡 After connecting, run these commands:"
echo "   1. conda activate ~/conda_envs/ollama_env/"
echo "   2. python llm_chat.py"
echo ""

# Just connect to GPU node - user will run conda commands manually
srun --jobid=42162557 --pty bash