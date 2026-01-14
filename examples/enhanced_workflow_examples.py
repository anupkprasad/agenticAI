"""
Example script demonstrating the enhanced LLM-powered MD workflow
"""
import logging
from agentic.md_workflow import MDWorkflow
from agentic.llm import LLMClient

def setup_logging():
    """Setup detailed logging for workflow tracking."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('enhanced_workflow.log'),
            logging.StreamHandler()
        ]
    )

def example_preprocessed_pdb():
    """Example: User has already preprocessed PDB"""
    
    print("\n=== Enhanced Workflow: Preprocessed PDB Example ===")
    
    workflow = MDWorkflow()
    
    result = workflow.run(
        user_goal="""I have a preprocessed PDB file at /data/protein_clean.pdb. 
                     The protein is already cleaned and ready for simulation setup. 
                     I want to run a 10ns MD simulation with AMBER force field.""",
        config={"working_directory": "/data/md_project"}
    )
    
    print("Final Report:")
    print(result.get("final_report", "No report generated"))

def example_complex_analysis():
    """Example: User wants specific analysis"""
    
    print("\n=== Enhanced Workflow: Complex Analysis Request ===")
    
    workflow = MDWorkflow()
    
    result = workflow.run(
        user_goal="""I need to analyze the conformational stability of my protein complex.
                     I have simulation trajectories from a 50ns GROMACS run.
                     Please calculate RMSD, RMSF, radius of gyration, and hydrogen bonds.
                     Also generate publication-quality plots for each analysis.""",
        config={
            "trajectory_path": "/data/traj.xtc",
            "topology_path": "/data/system.tpr"
        }
    )
    
    print("Analysis Results:")
    print(result.get("analysis_results", "No analysis completed"))

def example_full_pipeline():
    """Example: Complete pipeline from raw PDB"""
    
    print("\n=== Enhanced Workflow: Full Pipeline Example ===")
    
    workflow = MDWorkflow()
    
    result = workflow.run(
        user_goal="""I want to study the dynamics of lysozyme protein.
                     Please take the raw PDB file, clean it up, set up a water box simulation,
                     run it on our HPC cluster, and analyze the structural properties.
                     I'm interested in loop flexibility and binding site dynamics.""",
        config={
            "raw_pdb": "/data/lysozyme_raw.pdb",
            "target_simulation_time": "20ns",
            "force_field": "CHARMM36",
            "water_model": "TIP3P"
        }
    )
    
    print("Complete Workflow Results:")
    print(result.get("final_report", "Workflow incomplete"))

def example_troubleshooting():
    """Example: Enhanced error handling"""
    
    print("\n=== Enhanced Workflow: Error Handling Example ===")
    
    workflow = MDWorkflow()
    
    # Simulate a request with issues
    result = workflow.run(
        user_goal="""My simulation keeps crashing after 1ns. 
                     The system has weird waters and the temperature is unstable.
                     Can you help me figure out what's wrong and fix it?""",
        config={
            "problematic_files": "/data/bad_setup/",
            "previous_errors": ["LINCS warning", "Temperature coupling issue"]
        }
    )
    
    if not result.get("workflow_complete", False):
        print("Error Report:")
        print(result.get("error_report", "No error report available"))

def example_llm_vs_heuristic():
    """Example: Demonstrate LLM vs heuristic routing"""
    
    print("\n=== Enhanced Workflow: LLM vs Heuristic Routing ===")
    
    # Test with LLM available
    llm_workflow = MDWorkflow(llm_client=LLMClient())
    
    print("Testing with LLM available:")
    result_llm = llm_workflow.run(
        user_goal="PDB is already preprocessed, just need to run simulation"
    )
    print(f"LLM Routing Decision: {result_llm.get('supervisor_reasoning', 'No reasoning')}")
    
    # Test with LLM unavailable (mock)
    from unittest.mock import Mock
    mock_llm = Mock()
    mock_llm.available = False
    
    heuristic_workflow = MDWorkflow(llm_client=mock_llm)
    
    print("\nTesting with LLM unavailable (heuristic fallback):")
    result_heuristic = heuristic_workflow.run(
        user_goal="PDB is already preprocessed, just need to run simulation"
    )
    print(f"Heuristic routing used when LLM unavailable")

def demonstrate_enhanced_features():
    """Demonstrate enhanced features of the workflow"""
    
    print("\n=== Enhanced Features Demonstration ===")
    
    workflow = MDWorkflow()
    
    test_cases = [
        "PDB is already preprocessed, just need to run simulation",
        "I want to skip the HPC step and analyze existing trajectories", 
        "Only preprocess my protein, don't run any simulation",
        "My simulation failed, help me troubleshoot the issue"
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\nTest Case {i}: {case}")
        
        result = workflow.run(user_goal=case)
        
        # Print supervisor reasoning if available
        reasoning = result.get("supervisor_reasoning", "Heuristic routing used")
        print(f"Routing Logic: {reasoning}")
        print(f"Next Node: {result.get('next_node', 'Not determined')}")

def example_backward_compatibility():
    """Example: Show backward compatibility with existing interface"""
    
    print("\n=== Backward Compatibility Example ===")
    
    # Old style usage still works
    workflow = MDWorkflow()
    
    result = workflow.run(
        user_goal="Standard MD simulation workflow",
        config={
            "md_engine": "gromacs",
            "force_field": "amber99sb-ildn",
            "water_model": "tip3p"
        }
    )
    
    print("Backward compatible execution:")
    print(f"Status: {'Success' if result.get('workflow_complete') else 'Incomplete'}")
    print(f"Errors: {len(result.get('errors', []))}")

if __name__ == "__main__":
    setup_logging()
    
    print("=== Enhanced LLM-Powered MD Workflow Examples ===")
    
    # Check if LLM is available
    llm = LLMClient()
    if not llm.available:
        print("Warning: LLM not available, will use heuristic mode for demonstration")
    else:
        print("LLM available - will demonstrate enhanced reasoning capabilities")
    
    try:
        # Run examples
        example_preprocessed_pdb()
        example_complex_analysis()
        example_full_pipeline()
        example_troubleshooting()
        example_llm_vs_heuristic()
        demonstrate_enhanced_features()
        example_backward_compatibility()
        
    except Exception as e:
        print(f"Example execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    print("\nEnhanced workflow examples completed!")
    print("\nKey Enhancements:")
    print("✅ LLM-powered routing decisions with intelligent understanding")
    print("✅ Automatic step skipping based on user input")
    print("✅ Enhanced final report generation")
    print("✅ Fallback to heuristic routing when LLM unavailable") 
    print("✅ Backward compatibility with existing workflow interface")
    print("✅ Configuration-driven agent registry")
    print("✅ Comprehensive logging and reasoning transparency")
