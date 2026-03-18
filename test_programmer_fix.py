#!/usr/bin/env python3
"""Test if the programmer tools.py fix is actually being used"""

import sys
import os

# Clear any cached imports
for mod in list(sys.modules.keys()):
    if 'agentic' in mod or 'programmer' in mod:
        del sys.modules[mod]

# Now import fresh
from agentic.programmer.tools import generate_python_tool

# Test case: Try to generate a tool with dictionary literals in implementation
test_implementation = """
def test_tool(trajectory_file: str) -> dict:
    import MDAnalysis as mda
    results = []
    u = mda.Universe(trajectory_file)
    for ts in u.trajectory:
        data = {
            "frame": ts.frame,
            "time": ts.time,
            "x": 1.0
        }
        results.append(data)
    return {"success": True, "data": results}
"""

try:
    # Use the StructuredTool .run() method
    result = generate_python_tool.run({
        "tool_name": "test_com_tool",
        "description": "Test tool for COM calculation",
        "parameters": {"trajectory_file": {"type": "str", "description": "Path to trajectory"}},
        "implementation": test_implementation,
        "working_directory": "/tmp/test_programmer"
    })
    
    print("✅ SUCCESS: Tool generation completed without f-string error!")
    print(f"Result: {result.get('success')}")
    print(f"File: {result.get('file_path')}")
    
    if result.get("success"):
        # Check the generated file
        file_path = result.get("file_path")
        if file_path and os.path.exists(file_path):
            with open(file_path, 'r') as f:
                content = f.read()
                if '{"frame": ts.frame' in content:
                    print("✅ Dictionary literal correctly preserved in generated code!")
                else:
                    print("⚠️ Dictionary literal might have been corrupted")
    
except ValueError as e:
    if "Invalid format specifier" in str(e):
        print(f"❌ FAILED: F-string bug still present!")
        print(f"Error: {e}")
        
        # Check the source code
        import inspect
        source = inspect.getsource(generate_python_tool)
        if 'code_parts.append("        " + line)' in source:
            print("\n✅ Source code HAS the fix")
            print("⚠️ But somehow the old buggy version is being executed!")
        else:
            print("\n❌ Source code DOES NOT have the fix!")
    else:
        raise

except Exception as e:
    print(f"❌ Unexpected error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
