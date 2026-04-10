#!/usr/bin/env python3
"""Quick test for domain tool loading."""
import sys
sys.path.insert(0, ".")

from run_agenticAIWork import _load_agent_domain_tools

for cp in ['preprocess', 'setup', 'hpc', 'analysis', 'reporter']:
    tools, instructions = _load_agent_domain_tools(cp)
    print(f'{cp}: {len(tools)} tools loaded')
    if tools:
        print(f'  Names: {list(tools.keys())}')
    if instructions:
        print(f'  Instructions snippet: {instructions[:120]}...')
    print()

print("ALL DONE")
