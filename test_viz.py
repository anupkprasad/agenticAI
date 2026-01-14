#!/usr/bin/env python3
import sys
import os

print("🧪 Testing Visualization")
print("=" * 30)

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

try:
    print("1. Testing imports...")
    from agentic.workflow_visualizer import create_workflow_diagram
    print("✅ Import successful")
    
    print("2. Testing diagram creation...")
    success = create_workflow_diagram("test_diagram.png")
    print(f"✅ Creation result: {success}")
    
    if os.path.exists("test_diagram.png"):
        size = os.path.getsize("test_diagram.png")
        print(f"✅ File created! Size: {size} bytes")
    else:
        print("❌ File not created")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
