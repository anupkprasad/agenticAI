#!/usr/bin/env python
"""Quick test of the workflow"""
import subprocess
import sys

cmd = [
    "python", "run_agenticAIWork.py",
    "--goal", "Prepare MD simulation for ATP.pdb with AMBER force field",
    "--use-llm",
    "--llm-base-url", "http://127.0.0.1:11434",
    "--llm-model", "gpt-oss:20b",
    "--working-dir", "working_dir/ATP.pdb/",
    "--no-human-loop"
]

print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd, capture_output=False, text=True)
sys.exit(result.returncode)
