#!/usr/bin/env python3
"""
Demo: How to visualize your workflow programmatically

This shows different ways to create workflow diagrams:
1. Using the visualizer directly
2. Using the convenience function
3. Using the workflow method
"""

def demo_workflow_visualization():
    print("🎨 MD Workflow Visualization Demo")
    print("=" * 50)
    
    # Method 1: Direct visualizer usage
    print("\n1. 📊 Using WorkflowVisualizer directly...")
    from agentic.workflow_visualizer import WorkflowVisualizer, check_visualization_dependencies
    
    if check_visualization_dependencies():
        visualizer = WorkflowVisualizer()
        success = visualizer.visualize_workflow(output_file="demo_direct.png")
        if success:
            print("   ✅ Created: demo_direct.png")
        else:
            print("   ❌ Failed to create diagram")
    else:
        print("   ❌ Visualization dependencies not available")
    
    # Method 2: Convenience function
    print("\n2. 🔧 Using convenience function...")
    from agentic.workflow_visualizer import create_workflow_diagram
    
    success = create_workflow_diagram("demo_convenience.png")
    if success:
        print("   ✅ Created: demo_convenience.png")
    else:
        print("   ❌ Failed to create diagram")
    
    # Method 3: From workflow instance
    print("\n3. 🏗️  Using MDWorkflow method...")
    try:
        from agentic.md_workflow import MDWorkflow
        from agentic.llm import LLMClient
        
        # Create workflow instance
        llm = LLMClient(model="demo")
        workflow = MDWorkflow(llm)
        
        # Create visualization
        success = workflow.create_visualization("demo_workflow.png")
        if success:
            print("   ✅ Created: demo_workflow.png")
        else:
            print("   ❌ Failed to create diagram")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print(f"\n🎯 Summary:")
    print(f"   Use update_diagram.py for quick updates")
    print(f"   Use workflow.create_visualization() in your code")
    print(f"   Diagram reflects your actual LangGraph structure!")

if __name__ == "__main__":
    demo_workflow_visualization()
