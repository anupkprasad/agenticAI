#!/usr/bin/env python3
"""
MD Workflow Visualizer - Simple and Reliable

Usage:
    python visualize_workflow.py                    # Creates md_workflow_diagram.png
    python visualize_workflow.py my_diagram.png     # Creates custom named file
"""
import sys
import os

def main():
    print("🎨 MD Workflow Visualizer")
    print("=" * 40)
    
    # Get output filename
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
    else:
        output_file = "md_workflow_diagram.png"
    
    print(f"📊 Target file: {output_file}")
    
    # Add current directory to path for imports
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)
    
    try:
        print("� Importing visualization module...")
        from agentic.workflow_visualizer import create_workflow_diagram
        print("✅ Import successful!")
        
        print("🚀 Creating visualization...")
        success = create_workflow_diagram(output_file)
        
        if success:
            if os.path.exists(output_file):
                file_size = os.path.getsize(output_file)
                print(f"✅ SUCCESS! Created: {output_file}")
                print(f"� Size: {file_size:,} bytes")
                print(f"� Full path: {os.path.abspath(output_file)}")
            else:
                print(f"⚠️  Function returned success but file not found")
                return 1
        else:
            print("❌ Visualization creation failed")
            return 1
            
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        print("💡 Make sure you're in the right directory")
        return 1
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    exit_code = main()
    print(f"\n🏁 Script finished with exit code: {exit_code}")
    sys.exit(exit_code)
