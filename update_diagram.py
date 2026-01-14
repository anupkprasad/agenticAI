#!/usr/bin/env python3
"""Simple workflow diagram updater"""

from agentic.workflow_visualizer import create_workflow_diagram

if __name__ == "__main__":
    print("🔄 Updating workflow diagram...")
    success = create_workflow_diagram()
    if success:
        print("✅ Diagram updated successfully!")
        print("📂 Location: md_workflow_visualization.png")
    else:
        print("❌ Failed to update diagram")
